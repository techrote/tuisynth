"""padsynth - a cell-native pads / strings / air / ambience synthesiser.

Single runtime source (mirroring mdbm's one-file policy): DSP engine,
validated reconfigurable patch graph, mdbm-compatible skinning
(md-editor-theme/1.1 subset), manually-maintained config that the program
never rewrites, Windows-Terminal-first TUI with full keyboard parity for
every mouse action, plus offline WAV render / diagnostics / snapshot paths
that work with the standard library only.

Interface philosophy follows mdbm: tiles with independent memories,
one-cell draggable dividers, transactional theme preview, command palette
as the emergency route, protected focus/selection/menus, bounded local
session state. Visual language follows the sketch-journal references:
dense glyph fields, v0..v7 material ramps, uppercase letterspaced kickers,
field-shell panels with cap/foot lines.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import struct
import sys
import threading
import time
import wave

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

APP_ID = "padsynth"
APP_VERSION = "0.1.0"
PATCH_SCHEMA = "padsynth-patch/1.0"
CONFIG_SCHEMA = "padsynth-config/1.0"
THEME_SCHEMA = "md-editor-theme/1.1"
THEME_SCHEMA_LEGACY = "md-editor-theme/1.0"

ID_RE = re.compile(r"^[a-z][a-z0-9_.\-]{0,63}$")

# Glyph vocabularies drawn from the sketch-journal references.
GLYPH_DENSITY = [" ", ".", ",", ":", ";", "+", "x", "%", "#", "&",
                 "░", "▒", "▓", "╬", "╫", "█"]
GLYPH_SLASH = ["/", "\\", "|", "-", "+", "x"]
GLYPH_LEVEL = ["_", ".", "-", "=", "+", "*", "#", "█"]

AUDITION_CHORD = [45, 52, 57, 60, 64]  # A2 E3 A3 C4 E4 (Am add9, pad-friendly)


# --------------------------------------------------------------------------
# small utilities
# --------------------------------------------------------------------------

def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def stable_seed(text, salt=0):
    digest = hashlib.md5(text.encode("utf-8")).digest()
    return (int.from_bytes(digest[:8], "little") ^ (salt * 0x9E3779B1)) & 0xFFFFFFFF


def midi_to_freq(midi):
    return 440.0 * (2.0 ** ((float(midi) - 69.0) / 12.0))


_NOTE_BASE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def note_to_midi(token):
    """Parse 'C3', 'Eb4', 'F#2' or a plain MIDI integer string."""
    token = token.strip()
    if re.fullmatch(r"-?\d{1,3}", token):
        return clamp(int(token), 0, 127)
    m = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d)", token)
    if not m:
        raise ValueError("bad note %r (want like C3, Eb4, F#2 or 60)" % token)
    name, acc, octv = m.group(1).upper(), m.group(2), int(m.group(3))
    semi = _NOTE_BASE[name] + (1 if acc == "#" else -1 if acc == "b" else 0)
    return clamp(12 * (octv + 1) + semi, 0, 127)


def midi_to_name(midi):
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    midi = clamp(int(midi), 0, 127)
    return "%s%d" % (names[midi % 12], midi // 12 - 1)


def atomic_write_bytes(path, data):
    tmp = path + ".tmp-%d" % os.getpid()
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def atomic_write_text(path, text):
    atomic_write_bytes(path, text.encode("utf-8"))


# --------------------------------------------------------------------------
# reconfigurable patch graph
#
# A patch is JSON data (never code). Nodes are evaluated in dependency
# order regardless of file order. Supported blocks are allowlisted below;
# there are no executable expressions. Two evaluation stages:
#   voice stage: osc/string/noise sources summed per note through the
#     first filter_lp + amp_env, modulated by lfo/mod_route nodes.
#   bus stage:   mixer/chorus/delay/reverb/output nodes evaluated
#     recursively over whole-bus buffers in topological order.
# --------------------------------------------------------------------------

PARAM_SPECS = {
    # name: (kind, lo, hi, choices)
    "saw_mix": ("float", 0.0, 1.0, None),
    "pulse_mix": ("float", 0.0, 1.0, None),
    "sub_sine": ("float", 0.0, 1.0, None),
    "detune_cents": ("float", 0.0, 60.0, None),
    "octave": ("int", -2, 2, None),
    "gain": ("float", 0.0, 1.0, None),
    "voices": ("int", 1, 4, None),
    "spread_cents": ("float", 0.0, 50.0, None),
    "chorus_rate_hz": ("float", 0.02, 5.0, None),
    "chorus_depth_ms": ("float", 0.0, 12.0, None),
    "cutoff_hz": ("float", 40.0, 18000.0, None),
    "resonance": ("float", 0.0, 0.95, None),
    "env_amount": ("float", -1.0, 1.0, None),
    "key_track": ("float", 0.0, 1.0, None),
    "attack_s": ("float", 0.005, 8.0, None),
    "decay_s": ("float", 0.01, 8.0, None),
    "sustain": ("float", 0.0, 1.0, None),
    "release_s": ("float", 0.02, 12.0, None),
    "rate_hz": ("float", 0.02, 20.0, None),
    "shape": ("choice", None, None, ("sine", "tri", "square", "saw")),
    "src": ("choice", None, None, ("lfo1", "lfo2", "vel",)),
    "dst": ("choice", None, None, ("cutoff", "detune", "pan", "amp", "width")),
    "amount": ("float", -1.0, 1.0, None),
    "time_ms": ("float", 1.0, 2000.0, None),
    "feedback": ("float", 0.0, 0.9, None),
    "mix": ("float", 0.0, 1.0, None),
    "damp": ("float", 0.0, 1.0, None),
    "size": ("float", 0.0, 1.0, None),
    "width": ("float", 0.0, 1.5, None),
    "softclip": ("bool", None, None, None),
    "rate": ("float", 0.02, 5.0, None),
    "depth_ms": ("float", 0.0, 12.0, None),
}

NODE_TYPES = {
    "osc_stack": {
        "params": ("saw_mix", "pulse_mix", "sub_sine", "detune_cents", "octave", "gain"),
        "inputs": (),
        "stage": "voice",
    },
    "string_ensemble": {
        "params": ("voices", "spread_cents", "chorus_rate_hz", "chorus_depth_ms", "gain"),
        "inputs": (),
        "stage": "voice",
    },
    "noise_air": {
        "params": ("cutoff_hz", "gain",),
        "inputs": (),
        "stage": "voice",
    },
    "filter_lp": {
        "params": ("cutoff_hz", "resonance", "env_amount", "key_track"),
        "inputs": ("in",),
        "stage": "both",
    },
    "amp_env": {
        "params": ("attack_s", "decay_s", "sustain", "release_s"),
        "inputs": (),
        "stage": "voice",
    },
    "lfo": {
        "params": ("rate_hz", "shape"),
        "inputs": (),
        "stage": "voice",
    },
    "mod_route": {
        "params": ("src", "dst", "amount"),
        "inputs": ("lfo",),
        "stage": "voice",
    },
    "mixer": {
        "params": ("gain",),
        "inputs": None,  # any number of named inputs
        "stage": "bus",
    },
    "chorus": {
        "params": ("rate", "depth_ms", "mix"),
        "inputs": ("in",),
        "stage": "bus",
    },
    "delay": {
        "params": ("time_ms", "feedback", "mix", "damp"),
        "inputs": ("in",),
        "stage": "bus",
    },
    "reverb": {
        "params": ("size", "damp", "mix"),
        "inputs": ("in",),
        "stage": "bus",
    },
    "output": {
        "params": ("gain", "width", "softclip"),
        "inputs": ("in",),
        "stage": "bus",
    },
}

DEFAULT_PATCH = {
    "schema": PATCH_SCHEMA,
    "id": "weather-machine",
    "name": "Weather Machine",
    "description": "Compound pad: supersaw + string ensemble + air through a slow filter.",
    "nodes": [
        {"id": "osc1", "type": "osc_stack",
         "params": {"saw_mix": 0.7, "pulse_mix": 0.2, "sub_sine": 0.4,
                    "detune_cents": 12.0, "octave": 0, "gain": 0.5}},
        {"id": "ens1", "type": "string_ensemble",
         "params": {"voices": 3, "spread_cents": 18.0, "chorus_rate_hz": 0.15,
                    "chorus_depth_ms": 4.0, "gain": 0.4}},
        {"id": "air1", "type": "noise_air",
         "params": {"cutoff_hz": 6500.0, "gain": 0.12}},
        {"id": "lfo1", "type": "lfo", "params": {"rate_hz": 0.08, "shape": "sine"}},
        {"id": "lfo2", "type": "lfo", "params": {"rate_hz": 0.13, "shape": "tri"}},
        {"id": "route1", "type": "mod_route",
         "params": {"src": "lfo1", "dst": "cutoff", "amount": 0.45}, "inputs": {"lfo": "lfo1"}},
        {"id": "route2", "type": "mod_route",
         "params": {"src": "lfo2", "dst": "detune", "amount": 0.3}, "inputs": {"lfo": "lfo2"}},
        {"id": "route3", "type": "mod_route",
         "params": {"src": "lfo2", "dst": "pan", "amount": 0.5}, "inputs": {"lfo": "lfo2"}},
        {"id": "filt1", "type": "filter_lp",
         "params": {"cutoff_hz": 2200.0, "resonance": 0.25, "env_amount": 0.5, "key_track": 0.4},
         "inputs": {}},
        {"id": "env1", "type": "amp_env",
         "params": {"attack_s": 1.2, "decay_s": 2.0, "sustain": 0.75, "release_s": 3.0}},
        {"id": "mix1", "type": "mixer", "params": {"gain": 1.0},
         "inputs": {"a": "osc1", "b": "ens1", "c": "air1"}},
        {"id": "ch1", "type": "chorus", "params": {"rate": 0.4, "depth_ms": 3.0, "mix": 0.25},
         "inputs": {"in": "mix1"}},
        {"id": "dly1", "type": "delay",
         "params": {"time_ms": 375.0, "feedback": 0.35, "mix": 0.22, "damp": 0.4},
         "inputs": {"in": "ch1"}},
        {"id": "vrb1", "type": "reverb", "params": {"size": 0.75, "damp": 0.5, "mix": 0.4},
         "inputs": {"in": "dly1"}},
        {"id": "out", "type": "output", "params": {"gain": 0.8, "width": 1.0, "softclip": True},
         "inputs": {"in": "vrb1"}},
    ],
}


def _check_param_value(name, value):
    spec = PARAM_SPECS.get(name)
    if spec is None:
        return "unknown param %r" % name
    kind, lo, hi, choices = spec
    if kind == "float":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return "param %r wants a number" % name
        if not (lo - 1e-9 <= float(value) <= hi + 1e-9):
            return "param %r=%r out of range [%s, %s]" % (name, value, lo, hi)
    elif kind == "int":
        if not isinstance(value, int) or isinstance(value, bool):
            return "param %r wants an integer" % name
        if not (lo <= value <= hi):
            return "param %r=%r out of range [%d, %d]" % (name, value, lo, hi)
    elif kind == "bool":
        if not isinstance(value, bool):
            return "param %r wants true/false" % name
    elif kind == "choice":
        if value not in choices:
            return "param %r=%r not one of %s" % (name, value, "/".join(choices))
    return None


def validate_patch(patch):
    """Return a list of error strings; empty means the patch is usable."""
    errors = []
    if not isinstance(patch, dict):
        return ["patch must be a JSON object"]
    if patch.get("schema") != PATCH_SCHEMA:
        errors.append("schema must be %r" % PATCH_SCHEMA)
    pid = patch.get("id", "")
    if not isinstance(pid, str) or not ID_RE.match(pid):
        errors.append("bad patch id %r" % (pid,))
    nodes = patch.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return errors + ["patch needs a non-empty nodes array"]
    seen = {}
    for i, node in enumerate(nodes):
        where = "node #%d" % i
        if not isinstance(node, dict):
            errors.append("%s must be an object" % where)
            continue
        nid = node.get("id")
        ntype = node.get("type")
        if not isinstance(nid, str) or not ID_RE.match(nid):
            errors.append("%s has bad id %r" % (where, nid))
            continue
        if nid in seen:
            errors.append("duplicate node id %r" % nid)
        seen[nid] = node
        spec = NODE_TYPES.get(ntype)
        if spec is None:
            errors.append("%r: unknown type %r" % (nid, ntype))
            continue
        params = node.get("params", {})
        inputs = node.get("inputs", {})
        if not isinstance(params, dict):
            errors.append("%r: params must be an object" % nid)
            params = {}
        if not isinstance(inputs, dict):
            errors.append("%r: inputs must be an object" % nid)
            inputs = {}
        for pname, pval in params.items():
            if pname not in spec["params"]:
                errors.append("%r: unknown param %r for %s" % (nid, pname, ntype))
                continue
            err = _check_param_value(pname, pval)
            if err:
                errors.append("%r: %s" % (nid, err))
        allowed = spec["inputs"]
        if allowed is not None:
            for iname in inputs:
                if iname not in allowed:
                    errors.append("%r: unknown input %r for %s" % (nid, iname, ntype))
        for iname, target in inputs.items():
            if not isinstance(target, str) or target not in seen and target not in [n.get("id") for n in nodes if isinstance(n, dict)]:
                errors.append("%r: input %r references unknown node %r" % (nid, iname, target))
        # mod_route cross-checks: src names an lfo role, lfo input names the node.
        if ntype == "mod_route" and isinstance(params, dict):
            src = params.get("src")
            if src in ("lfo1", "lfo2") and "lfo" in inputs:
                want = {"lfo1": "lfo1", "lfo2": "lfo2"}.get(src)
                if inputs["lfo"] != want and inputs["lfo"] not in seen:
                    pass  # already reported above
    outs = [n.get("id") for n in nodes if isinstance(n, dict) and n.get("type") == "output"]
    if len(outs) == 0:
        errors.append("patch needs exactly one output node (none found)")
    elif len(outs) > 1:
        errors.append("patch needs exactly one output node (%d found)" % len(outs))
    # cycle check only if refs are otherwise sane
    order, cycle = topo_order(patch)
    if cycle:
        errors.append("cycle detected: %s" % " -> ".join(cycle))
    return errors


def topo_order(patch):
    """Dependency order for node ids. Returns (order, cycle_or_None)."""
    nodes = {n["id"]: n for n in patch.get("nodes", []) if isinstance(n, dict) and "id" in n}
    state = {}  # 0=unvisited 1=in-stack 2=done
    order = []
    cycle = []

    def visit(nid, stack):
        st = state.get(nid, 0)
        if st == 2:
            return True
        if st == 1:
            cycle.extend(stack[stack.index(nid):] + [nid])
            return False
        state[nid] = 1
        node = nodes.get(nid)
        if node is not None:
            for target in (node.get("inputs") or {}).values():
                if target in nodes:
                    if not visit(target, stack + [nid]):
                        return False
        state[nid] = 2
        order.append(nid)
        return True

    for nid in sorted(nodes):
        if state.get(nid, 0) == 0:
            if not visit(nid, []):
                return [], cycle
    return order, None


def patch_node_map(patch):
    return {n["id"]: n for n in patch.get("nodes", []) if isinstance(n, dict)}


# --------------------------------------------------------------------------
# DSP engine (standard library only, deterministic)
# --------------------------------------------------------------------------

_TWO_PI = 2.0 * math.pi


def adsr_level(t, hold, a, d, s, r):
    if t < 0:
        return 0.0
    if t < a:
        return t / a if a > 0 else 1.0
    t -= a
    if t < hold:
        # decay from 1 to sustain across d, then hold sustain
        k = min(1.0, t / d) if d > 0 else 1.0
        return 1.0 + (s - 1.0) * k
    t -= hold
    if t < r:
        return s * (1.0 - t / r) if r > 0 else 0.0
    return 0.0


def lfo_shape_value(shape, phase):
    p = phase % 1.0
    if shape == "sine":
        return math.sin(_TWO_PI * p)
    if shape == "tri":
        return 4.0 * p - 1.0 if p < 0.5 else 3.0 - 4.0 * p
    if shape == "square":
        return 1.0 if p < 0.5 else -1.0
    if shape == "saw":
        return 2.0 * p - 1.0
    return math.sin(_TWO_PI * p)


def biquad_lp_coeffs(cutoff, q, sr):
    cutoff = clamp(cutoff, 20.0, sr * 0.45)
    q = clamp(q, 0.3, 14.0)
    w0 = _TWO_PI * cutoff / sr
    cosw = math.cos(w0)
    sinw = math.sin(w0)
    alpha = sinw / (2.0 * q)
    b0 = (1.0 - cosw) / 2.0
    b1 = 1.0 - cosw
    b2 = (1.0 - cosw) / 2.0
    a0 = 1.0 + alpha
    a1 = -2.0 * cosw
    a2 = 1.0 - alpha
    return b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0


def _resonance_to_q(resonance):
    return 0.5 + (float(resonance) ** 1.5) * 11.5


def _collect_voice_params(nodemap):
    filt = None
    env = None
    lfos = {}
    routes = []
    for nid, node in nodemap.items():
        ntype = node.get("type")
        if ntype == "filter_lp" and filt is None:
            filt = dict(node.get("params", {}))
        elif ntype == "amp_env" and env is None:
            env = dict(node.get("params", {}))
        elif ntype == "lfo":
            lfos[nid] = dict(node.get("params", {}))
        elif ntype == "mod_route":
            routes.append({"params": dict(node.get("params", {})),
                           "lfo": (node.get("inputs") or {}).get("lfo")})
    if filt is None:
        filt = {"cutoff_hz": 4000.0, "resonance": 0.2, "env_amount": 0.3, "key_track": 0.3}
    if env is None:
        env = {"attack_s": 0.8, "decay_s": 1.5, "sustain": 0.7, "release_s": 2.5}
    return filt, env, lfos, routes


def _route_amount(routes, lfos, dst, t_global, vel):
    total = 0.0
    for route in routes:
        params = route["params"]
        if params.get("dst") != dst:
            continue
        src = params.get("src")
        amount = float(params.get("amount", 0.0))
        if src == "vel":
            total += amount * (2.0 * vel - 1.0)
        elif src in ("lfo1", "lfo2"):
            node_id = route.get("lfo") or src
            spec = lfos.get(node_id)
            if spec is None:
                continue
            phase = t_global * float(spec.get("rate_hz", 0.1))
            total += amount * lfo_shape_value(spec.get("shape", "sine"), phase)
    return total


def _render_voice_note(nodemap, filt, env, lfos, routes, midi, vel, hold, total, sr, rng):
    n = int(sr * total)
    buf = [0.0] * n
    freq = midi_to_freq(midi)
    detune_mod = 0.0
    # per-note static detune wander from routes evaluated at t=0 is dynamic; keep simple
    noise_lp = 0.0
    noise_nodes = [(nid, node) for nid, node in nodemap.items() if node.get("type") == "noise_air"]
    noise_cut = float(noise_nodes[0][1].get("params", {}).get("cutoff_hz", 6500.0)) if noise_nodes else 6500.0
    noise_gain = sum(float(node.get("params", {}).get("gain", 0.0)) for _, node in noise_nodes)
    noise_alpha = clamp(_TWO_PI * noise_cut / sr, 0.001, 1.0)
    # biquad state, coeffs refreshed per block
    x1 = x2 = y1 = y2 = 0.0
    b0 = b1 = b2 = a1 = a2 = 0.0
    b0, b1, b2, a1, a2 = biquad_lp_coeffs(filt["cutoff_hz"], _resonance_to_q(filt["resonance"]), sr)
    q = _resonance_to_q(filt["resonance"])
    base_cut = float(filt["cutoff_hz"])
    env_amt = float(filt.get("env_amount", 0.0))
    key_track = float(filt.get("key_track", 0.0))
    key_mul = 2.0 ** ((key_track * (midi - 60.0)) / 12.0)
    a, d, s, r = (float(env["attack_s"]), float(env["decay_s"]),
                  float(env["sustain"]), float(env["release_s"]))
    pan_base = ((stable_seed("pan%d" % midi, 3) % 2000) / 1000.0 - 1.0) * 0.3
    osc_nodes = [(nid, node) for nid, node in nodemap.items()
                 if node.get("type") in ("osc_stack", "string_ensemble")]
    block = 32
    for start in range(0, n, block):
        t_mid = (start + block / 2) / sr
        cut_mod = _route_amount(routes, lfos, "cutoff", t_mid, vel)
        det_mod = _route_amount(routes, lfos, "detune", t_mid, vel)
        cutoff = base_cut * key_mul * (2.0 ** (env_amt * 2.0 * (adsr_level(t_mid, hold, a, d, s, r) - 0.5)
                                               + cut_mod * 1.5))
        b0, b1, b2, a1, a2 = biquad_lp_coeffs(cutoff, q, sr)
        detune_mod = det_mod * 25.0
        for i in range(start, min(start + block, n)):
            t = i / sr
            level = adsr_level(t, hold, a, d, s, r)
            if level <= 0.0:
                continue
            sample = 0.0
            for nid, node in osc_nodes:
                params = node.get("params", {})
                if node.get("type") == "osc_stack":
                    det = float(params.get("detune_cents", 10.0)) + detune_mod
                    ratio = 2.0 ** (det / 2400.0)
                    octv = int(params.get("octave", 0))
                    f = freq * (2.0 ** octv)
                    ph1 = (t * f * ratio) % 1.0
                    ph2 = (t * f / ratio) % 1.0
                    saw = (2.0 * ph1 - 1.0) * 0.5 + (2.0 * ph2 - 1.0) * 0.5
                    pulse = 1.0 if ph1 < 0.5 else -1.0
                    sub = math.sin(_TWO_PI * ((t * f / 2.0) % 1.0))
                    sample += float(params.get("gain", 0.5)) * (
                        float(params.get("saw_mix", 0.7)) * saw * 0.6
                        + float(params.get("pulse_mix", 0.0)) * pulse * 0.35
                        + float(params.get("sub_sine", 0.3)) * sub * 0.5)
                else:  # string_ensemble
                    vcount = int(params.get("voices", 2))
                    spread = float(params.get("spread_cents", 15.0)) + detune_mod * 0.5
                    crate = float(params.get("chorus_rate_hz", 0.2))
                    cdepth = float(params.get("chorus_depth_ms", 3.0))
                    acc = 0.0
                    for v in range(vcount):
                        off = (v - (vcount - 1) / 2.0) * spread
                        wob = math.sin(_TWO_PI * (crate * t + v * 0.37)) * cdepth * 0.001 * freq
                        ph = (t * freq * (2.0 ** (off / 1200.0)) + wob) % 1.0
                        acc += 2.0 * ph - 1.0
                    sample += float(params.get("gain", 0.4)) * acc / max(1, vcount) * 0.7
            if noise_gain > 0.0:
                white = rng.uniform(-1.0, 1.0)
                noise_lp += noise_alpha * (white - noise_lp)
                sample += noise_gain * noise_lp * 2.0
            # biquad lowpass
            y0 = b0 * sample + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
            x2, x1, y2, y1 = x1, sample, y1, y0
            buf[i] = y0 * level
    # stereo pan (equal power), dynamic pan mod at note midpoint
    pan = clamp(pan_base + _route_amount(routes, lfos, "pan", hold / 2.0, vel) * 0.6, -1.0, 1.0)
    ang = (pan + 1.0) * math.pi / 4.0
    gl, gr = math.cos(ang), math.sin(ang)
    amp_mod = 1.0 + _route_amount(routes, lfos, "amp", hold / 2.0, vel) * 0.25
    left = [v * gl * amp_mod * (0.35 + 0.65 * vel) for v in buf]
    right = [v * gr * amp_mod * (0.35 + 0.65 * vel) for v in buf]
    return left, right


def render_dry(patch, notes, seconds, sr, seed):
    nodemap = patch_node_map(patch)
    filt, env, lfos, routes = _collect_voice_params(nodemap)
    n = int(sr * seconds)
    left = [0.0] * n
    right = [0.0] * n
    for note in notes:
        midi = int(note["midi"])
        vel = float(note.get("vel", 0.8))
        start = float(note.get("start", 0.0))
        dur = float(note.get("dur", seconds))
        hold = max(0.05, min(dur, seconds - start))
        total = seconds - start
        if total <= 0.05:
            continue
        rng = random.Random(stable_seed("%s:%d" % (patch.get("id", "x"), midi), seed))
        vl, vr = _render_voice_note(nodemap, filt, env, lfos, routes, midi, vel, hold, total, sr, rng)
        off = int(sr * start)
        for i in range(min(len(vl), n - off)):
            left[off + i] += vl[i]
            right[off + i] += vr[i]
    # headroom for stacked voices
    k = 0.9 / max(1.0, math.sqrt(max(1, len(notes))))
    return [v * k for v in left], [v * k for v in right]


# -- bus FX (whole-buffer, memoized over the graph) -------------------------

def _apply_chorus(stereo, rate, depth_ms, mix, sr):
    left, right = stereo
    n = len(left)
    depth = int(sr * depth_ms / 1000.0)
    base = int(sr * 0.018)
    if depth < 1:
        return left, right
    out_l = [0.0] * n
    out_r = [0.0] * n
    for i in range(n):
        t = i / sr
        d1 = base + int(depth * (0.5 + 0.5 * math.sin(_TWO_PI * rate * t)))
        d2 = base + int(depth * (0.5 + 0.5 * math.sin(_TWO_PI * rate * t + math.pi)))
        j1 = i - d1
        j2 = i - d2
        w1 = left[j1] if j1 >= 0 else 0.0
        w2 = right[j2] if j2 >= 0 else 0.0
        out_l[i] = left[i] * (1.0 - mix * 0.5) + w1 * mix * 0.5
        out_r[i] = right[i] * (1.0 - mix * 0.5) + w2 * mix * 0.5
    return out_l, out_r


def _apply_delay(stereo, time_ms, feedback, mix, damp, sr):
    left, right = stereo
    n = len(left)
    d = max(1, int(sr * time_ms / 1000.0))
    buf_l = [0.0] * d
    buf_r = [0.0] * d
    lp_l = lp_r = 0.0
    alpha = clamp(0.15 + damp * 0.6, 0.05, 0.9)
    out_l = [0.0] * n
    out_r = [0.0] * n
    for i in range(n):
        p = i % d
        echo_l = buf_l[p]
        echo_r = buf_r[p]
        out_l[i] = left[i] * (1.0 - mix) + echo_l * mix
        out_r[i] = right[i] * (1.0 - mix) + echo_r * mix
        lp_l += alpha * ((left[i] + echo_l * feedback) - lp_l)
        lp_r += alpha * ((right[i] + echo_r * feedback) - lp_r)
        buf_l[p] = lp_l
        buf_r[p] = lp_r
    return out_l, out_r


def _comb_process(x, delay, fb, damp):
    n = len(x)
    buf = [0.0] * delay
    lp = 0.0
    alpha = clamp(0.2 + damp * 0.5, 0.05, 0.9)
    out = [0.0] * n
    for i in range(n):
        p = i % delay
        v = buf[p]
        lp += alpha * (v - lp)
        out[i] = v
        buf[p] = x[i] + lp * fb
    return out


def _allpass_process(x, delay, fb=0.5):
    n = len(x)
    buf = [0.0] * delay
    out = [0.0] * n
    for i in range(n):
        p = i % delay
        v = buf[p]
        out[i] = -x[i] + v
        buf[p] = x[i] + v * fb
    return out


def _apply_reverb(stereo, size, damp, mix, sr):
    left, right = stereo
    n = len(left)
    scale = 0.5 + size * 1.1
    base = [1116, 1188, 1277, 1356]
    fb = clamp(0.45 + size * 0.38 * (1.0 - 0.45 * damp), 0.0, 0.92)
    mono = [(left[i] + right[i]) * 0.5 for i in range(n)]
    wet_l = [0.0] * n
    wet_r = [0.0] * n
    for k, bd in enumerate(base):
        dl = max(16, int(bd * scale * (0.995 if k % 2 else 1.005)))
        c = _comb_process(mono, dl, fb, damp)
        if k % 2 == 0:
            wet_l = [a + b for a, b in zip(wet_l, c)]
        else:
            wet_r = [a + b for a, b in zip(wet_r, c)]
    wet_l = [v * 0.5 for v in wet_l]
    wet_r = [v * 0.5 for v in wet_r]
    wet_l = _allpass_process(_allpass_process(wet_l, max(16, int(556 * scale))), max(16, int(441 * scale)))
    wet_r = _allpass_process(_allpass_process(wet_r, max(16, int(548 * scale))), max(16, int(437 * scale)))
    return ([lv * (1.0 - mix) + w * mix for lv, w in zip(left, wet_l)],
            [rv * (1.0 - mix) + w * mix for rv, w in zip(right, wet_r)])


def _apply_width(stereo, width):
    left, right = stereo
    out_l, out_r = [], []
    for lv, rv in zip(left, right):
        mid = (lv + rv) * 0.5
        side = (lv - rv) * 0.5 * width
        out_l.append(mid + side)
        out_r.append(mid - side)
    return out_l, out_r


def _apply_softclip(stereo):
    return ([math.tanh(v) for v in stereo[0]], [math.tanh(v) for v in stereo[1]])


def eval_bus(patch, dry, sr):
    """Evaluate bus-stage nodes over whole buffers, memoized, in topo order."""
    nodemap = patch_node_map(patch)
    order, cycle = topo_order(patch)
    if cycle:
        raise ValueError("cyclic patch: %s" % " -> ".join(cycle))
    memo = {}

    def node_buffer(nid):
        if nid in memo:
            return memo[nid]
        node = nodemap[nid]
        ntype = node.get("type")
        params = node.get("params", {})
        inputs = node.get("inputs", {})
        if ntype in ("osc_stack", "string_ensemble", "noise_air", "amp_env", "lfo", "mod_route"):
            buf = dry  # voice-stage sources already summed into dry
        elif ntype == "mixer":
            acc_l = [0.0] * len(dry[0])
            acc_r = [0.0] * len(dry[1])
            if not inputs:
                acc_l, acc_r = dry
            else:
                for target in inputs.values():
                    bl, br = node_buffer(target)
                    acc_l = [a + b for a, b in zip(acc_l, bl)]
                    acc_r = [a + b for a, b in zip(acc_r, br)]
            g = float(params.get("gain", 1.0))
            buf = ([v * g for v in acc_l], [v * g for v in acc_r])
        elif ntype == "filter_lp":
            src = node_buffer(inputs.get("in")) if inputs.get("in") else dry
            b0, b1, b2, a1, a2 = biquad_lp_coeffs(
                float(params.get("cutoff_hz", 4000.0)),
                _resonance_to_q(float(params.get("resonance", 0.2))), sr)
            outs = []
            for ch in src:
                x1 = x2 = y1 = y2 = 0.0
                o = [0.0] * len(ch)
                for i, s in enumerate(ch):
                    y0 = b0 * s + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
                    x2, x1, y2, y1 = x1, s, y1, y0
                    o[i] = y0
                outs.append(o)
            buf = (outs[0], outs[1])
        elif ntype == "chorus":
            src = node_buffer(inputs.get("in")) if inputs.get("in") else dry
            buf = _apply_chorus(src, float(params.get("rate", 0.4)),
                                float(params.get("depth_ms", 3.0)), float(params.get("mix", 0.25)), sr)
        elif ntype == "delay":
            src = node_buffer(inputs.get("in")) if inputs.get("in") else dry
            buf = _apply_delay(src, float(params.get("time_ms", 350.0)),
                               float(params.get("feedback", 0.35)), float(params.get("mix", 0.2)),
                               float(params.get("damp", 0.4)), sr)
        elif ntype == "reverb":
            src = node_buffer(inputs.get("in")) if inputs.get("in") else dry
            buf = _apply_reverb(src, float(params.get("size", 0.7)),
                                float(params.get("damp", 0.5)), float(params.get("mix", 0.35)), sr)
        elif ntype == "output":
            src = node_buffer(inputs.get("in")) if inputs.get("in") else dry
            buf = _apply_width(src, float(params.get("width", 1.0)))
            if params.get("softclip", True):
                buf = _apply_softclip(buf)
            g = float(params.get("gain", 0.8))
            buf = ([clamp(v * g, -1.0, 1.0) for v in buf[0]],
                   [clamp(v * g, -1.0, 1.0) for v in buf[1]])
        else:
            buf = dry
        memo[nid] = buf
        return buf

    outs = [nid for nid in order if nodemap[nid].get("type") == "output"]
    if not outs:
        raise ValueError("no output node")
    return node_buffer(outs[0])


def make_chord(midis, seconds, vel=0.8):
    return [{"midi": int(m), "start": 0.0, "dur": max(0.1, seconds - 0.4), "vel": vel} for m in midis]


def render_patch(patch, notes, seconds, sr=44100, seed=7):
    errors = validate_patch(patch)
    if errors:
        raise ValueError("invalid patch: %s" % "; ".join(errors[:4]))
    sr = int(clamp(int(sr), 4000, 96000))
    seconds = clamp(float(seconds), 0.1, 60.0)
    dry = render_dry(patch, notes, seconds, sr, int(seed))
    return eval_bus(patch, dry, sr)


def buffer_peak(stereo):
    peak = 0.0
    for ch in stereo:
        for v in ch:
            a = abs(v)
            if a > peak:
                peak = a
    return peak


def write_wav(path, stereo, sr):
    left, right = stereo
    n = min(len(left), len(right))
    frames = bytearray()
    for i in range(n):
        frames += struct.pack("<h", int(clamp(left[i], -1.0, 1.0) * 32767.0))
        frames += struct.pack("<h", int(clamp(right[i], -1.0, 1.0) * 32767.0))
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(frames))
    return path


# --------------------------------------------------------------------------
# live audio backends (probed in order, always with an explicit report)
# --------------------------------------------------------------------------

_audio_state = {"playing": False, "backend": "null", "detail": "silent", "thread": None,
                "stop_flag": False, "generation": 0}


def probe_audio(prefer="auto"):
    """Return (backend, detail). Never raises; 'null' is always available."""
    order = ["sounddevice", "winsound", "null"] if prefer in ("auto", None) else [prefer, "null"]
    for name in order:
        if name == "sounddevice":
            try:
                import sounddevice as sd
                devs = sd.query_devices()
                outs = [d for d in devs if d.get("max_output_channels", 0) > 0]
                if outs:
                    return "sounddevice", "%d output device(s)" % len(outs)
            except Exception:
                continue
        elif name == "winsound":
            try:
                import winsound  # noqa: F401  (Windows stdlib only)
                return "winsound", "async temp-WAV playback"
            except Exception:
                continue
        elif name == "null":
            return "null", "offline WAV render only"
    return "null", "offline WAV render only"


def _play_winsound(stereo, sr, seconds):
    import tempfile
    import winsound
    fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="padsynth-")
    os.close(fd)
    try:
        write_wav(tmp, stereo, sr)
        winsound.PlaySound(tmp, winsound.SND_FILENAME | winsound.SND_ASYNC)
        # Block for the sound's duration (or until stopped), then purge so
        # the temp file can be removed. SND_ASYNC alone would leak the wait.
        deadline = time.time() + max(0.2, seconds + 0.4)
        while not _audio_state["stop_flag"] and time.time() < deadline:
            time.sleep(0.05)
        winsound.PlaySound(None, winsound.SND_PURGE)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _play_sounddevice(stereo, sr, loop):
    import sounddevice as sd
    import numpy as np
    data = np.column_stack([np.asarray(stereo[0], dtype=np.float32),
                            np.asarray(stereo[1], dtype=np.float32)])
    _audio_state["detail"] = "sounddevice stream @%dHz" % sr
    if loop:
        sd.play(data, sr, loop=True)
        while not _audio_state["stop_flag"]:
            time.sleep(0.05)
        sd.stop()
    else:
        sd.play(data, sr, blocking=True)


def _play_spec(stereo, sr, backend, loop):
    if backend == "sounddevice":
        _play_sounddevice(stereo, sr, loop)
    elif backend == "winsound" and not loop:
        _play_winsound(stereo, sr, len(stereo[0]) / float(sr))
    else:
        # null backend or winsound loop: hold the state, render only
        span = len(stereo[0]) / float(sr) if not loop else 0.4
        t0 = time.time()
        while not _audio_state["stop_flag"] and (loop or time.time() - t0 < span):
            time.sleep(0.05)


def play_buffer_async(stereo, sr, backend, loop=False, notify=None):
    """Play an already-rendered buffer without blocking. Single-flight."""
    stop_playback()
    return _play_spec_async((list(stereo[0]), list(stereo[1])), int(sr),
                            backend, bool(loop), notify)


def _play_spec_async(stereo, sr, backend, loop, notify):
    # Internal: assumes stop_playback() was already called.
    _audio_state["stop_flag"] = False
    _audio_state.pop("error", None)

    def worker():
        _audio_state["playing"] = True
        try:
            _play_spec(stereo, sr, backend, loop)
        except Exception as exc:
            _audio_state["error"] = str(exc)
        finally:
            _audio_state["playing"] = False
            if notify is not None:
                try:
                    notify()
                except Exception:
                    pass

    th = threading.Thread(target=worker, daemon=True)
    _audio_state["thread"] = th
    th.start()
    return th


def audition_async(patch, notes, seconds, sr, seed, backend, loop=False, notify=None):
    """Render in a worker thread, then play. Single-flight: stops previous.

    Returns immediately so the TUI never blocks on a multi-second render.
    Completion or failure is reported through notify(), which the TUI wires
    to a thread-safe repaint; without it, failures land in
    _audio_state['error'] for the status line to pick up.
    """
    import copy
    snapshot = copy.deepcopy(patch)
    notes = list(notes)
    seconds = float(seconds)
    sr = int(sr)
    seed = int(seed)

    # render inline just long enough to fail fast on invalid patches; the
    # heavy lifting stays in the worker. Validation is cheap, render is not,
    # so validate synchronously and render asynchronously.
    errors = validate_patch(snapshot)
    if errors:
        raise ValueError("invalid patch: %s" % "; ".join(errors[:4]))
    stop_playback()
    gen = _audio_state["generation"]

    def render_worker():
        try:
            stereo = render_patch(snapshot, notes, seconds, sr, seed)
        except Exception as exc:
            _audio_state["error"] = str(exc)
            if notify is not None:
                try:
                    notify()
                except Exception:
                    pass
            return
        if _audio_state["generation"] != gen:
            return  # superseded by a newer audition; drop silently
        _play_spec_async(stereo, sr, backend, loop, notify)

    th = threading.Thread(target=render_worker, daemon=True)
    _audio_state["thread"] = th
    th.start()
    return th


def stop_playback():
    _audio_state["generation"] = _audio_state.get("generation", 0) + 1
    _audio_state["stop_flag"] = True
    th = _audio_state.get("thread")
    if th is not None and th.is_alive():
        th.join(timeout=1.0)
    _audio_state["thread"] = None
    _audio_state["playing"] = False


# --------------------------------------------------------------------------
# configuration (TOML data; the program never rewrites this file)
# --------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "application": {"state_directory": ".padsynth"},
    "layout": {"pads_visible": True, "voice_visible": True, "mod_visible": True,
               "browser_visible": True, "piano_visible": True,
               "left_ratio": 0.24, "center_ratio": 0.40,
               "voice_ratio": 0.55, "min_width": 14, "min_height": 4},
    "appearance": {"theme": "neon-circuitry", "theme_directories": ["themes"],
                   "immersive": False, "seed": -1, "motion": "normal"},
    "capabilities": {"colour_depth": "auto", "unicode": True, "mouse": True,
                     "terminal_focus": True},
    "audio": {"sample_rate": 44100, "polyphony": 8, "audition_seconds": 2.5,
              "master_gain": 0.8, "device": "auto"},
    "accessibility": {"high_contrast": False, "reduced_motion": False, "ascii_only": False},
    "session": {"restore": True, "recovery_seconds": 5, "fps": 12, "paint_budget": 200000},
    "bindings": {},
}

EMERGENCY_COMMANDS = {"palette.open", "layout.restore", "quit.request", "ribbon.focus", "help.show"}
EMERGENCY_KEYS = {"c-p", "c-t", "c-q", "f10", "f1"}


def _coerce_bool(v):
    if isinstance(v, bool):
        return v
    raise ValueError("want true/false")


def load_config(path):
    """Load TOML config with per-value fallback. Returns (cfg, diagnostics)."""
    import copy
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    diagnostics = []
    if tomllib is None:
        diagnostics.append("tomllib unavailable: using defaults")
        return cfg, diagnostics
    if not os.path.isfile(path):
        diagnostics.append("no config at %s: using defaults" % path)
        return cfg, diagnostics
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except Exception as exc:
        diagnostics.append("config parse failed (%s): using defaults" % exc)
        return cfg, diagnostics
    if not isinstance(data, dict):
        diagnostics.append("config root must be a table: using defaults")
        return cfg, diagnostics
    if data.get("schema", CONFIG_SCHEMA) != CONFIG_SCHEMA:
        diagnostics.append("config schema %r != %r (continuing with fallbacks)"
                           % (data.get("schema"), CONFIG_SCHEMA))

    def section(name):
        sec = data.get(name, {})
        return sec if isinstance(sec, dict) else {}

    # layout -------------------------------------------------------------
    for key in ("pads_visible", "voice_visible", "mod_visible", "browser_visible",
                "piano_visible"):
        if key in section("layout"):
            try:
                cfg["layout"][key] = _coerce_bool(section("layout")[key])
            except ValueError:
                diagnostics.append("layout.%s invalid: keeping %r" % (key, cfg["layout"][key]))
    for key in ("left_ratio", "center_ratio", "voice_ratio"):
        if key in section("layout"):
            v = section("layout")[key]
            if isinstance(v, (int, float)) and 0.1 <= float(v) <= 0.8:
                cfg["layout"][key] = float(v)
            else:
                diagnostics.append("layout.%s invalid: keeping %s" % (key, cfg["layout"][key]))
    for key in ("min_width", "min_height"):
        if key in section("layout"):
            v = section("layout")[key]
            if isinstance(v, int) and 4 <= v <= 60:
                cfg["layout"][key] = v
            else:
                diagnostics.append("layout.%s invalid: keeping %d" % (key, cfg["layout"][key]))
    # appearance ----------------------------------------------------------
    app = section("appearance")
    if "theme" in app:
        if isinstance(app["theme"], str) and ID_RE.match(app["theme"]):
            cfg["appearance"]["theme"] = app["theme"]
        else:
            diagnostics.append("appearance.theme invalid: keeping %r" % cfg["appearance"]["theme"])
    if "theme_directories" in app:
        if (isinstance(app["theme_directories"], list)
                and all(isinstance(x, str) for x in app["theme_directories"])):
            cfg["appearance"]["theme_directories"] = app["theme_directories"]
        else:
            diagnostics.append("appearance.theme_directories invalid: keeping default")
    if "immersive" in app:
        try:
            cfg["appearance"]["immersive"] = _coerce_bool(app["immersive"])
        except ValueError:
            diagnostics.append("appearance.immersive invalid: keeping False")
    if "seed" in app:
        if isinstance(app["seed"], int) and -1 <= app["seed"] <= 2 ** 31 - 1:
            cfg["appearance"]["seed"] = app["seed"]
        else:
            diagnostics.append("appearance.seed invalid: keeping -1")
    if "motion" in app:
        if app["motion"] in ("off", "reduced", "normal", "high"):
            cfg["appearance"]["motion"] = app["motion"]
        else:
            diagnostics.append("appearance.motion invalid: keeping 'normal'")
    # capabilities ---------------------------------------------------------
    caps = section("capabilities")
    if "colour_depth" in caps:
        if caps["colour_depth"] in ("auto", "truecolour", "256", "16", "mono"):
            cfg["capabilities"]["colour_depth"] = caps["colour_depth"]
        else:
            diagnostics.append("capabilities.colour_depth invalid: keeping 'auto'")
    for key in ("unicode", "mouse", "terminal_focus"):
        if key in caps:
            try:
                cfg["capabilities"][key] = _coerce_bool(caps[key])
            except ValueError:
                diagnostics.append("capabilities.%s invalid: keeping %r" % (key, cfg["capabilities"][key]))
    # audio -----------------------------------------------------------------
    aud = section("audio")
    if "sample_rate" in aud:
        if isinstance(aud["sample_rate"], int) and 4000 <= aud["sample_rate"] <= 96000:
            cfg["audio"]["sample_rate"] = aud["sample_rate"]
        else:
            diagnostics.append("audio.sample_rate invalid: keeping 44100")
    if "polyphony" in aud:
        if isinstance(aud["polyphony"], int) and 1 <= aud["polyphony"] <= 16:
            cfg["audio"]["polyphony"] = aud["polyphony"]
        else:
            diagnostics.append("audio.polyphony invalid: keeping 8")
    if "audition_seconds" in aud:
        v = aud["audition_seconds"]
        if isinstance(v, (int, float)) and 0.5 <= float(v) <= 12.0:
            cfg["audio"]["audition_seconds"] = float(v)
        else:
            diagnostics.append("audio.audition_seconds invalid: keeping 2.5")
    if "master_gain" in aud:
        v = aud["master_gain"]
        if isinstance(v, (int, float)) and 0.0 <= float(v) <= 1.5:
            cfg["audio"]["master_gain"] = float(v)
        else:
            diagnostics.append("audio.master_gain invalid: keeping 0.8")
    if "device" in aud:
        if isinstance(aud["device"], str):
            cfg["audio"]["device"] = aud["device"]
        else:
            diagnostics.append("audio.device invalid: keeping 'auto'")
    # accessibility ------------------------------------------------------------
    acc = section("accessibility")
    for key in ("high_contrast", "reduced_motion", "ascii_only"):
        if key in acc:
            try:
                cfg["accessibility"][key] = _coerce_bool(acc[key])
            except ValueError:
                diagnostics.append("accessibility.%s invalid: keeping False" % key)
    # session ------------------------------------------------------------------
    ses = section("session")
    if "restore" in ses:
        try:
            cfg["session"]["restore"] = _coerce_bool(ses["restore"])
        except ValueError:
            diagnostics.append("session.restore invalid: keeping True")
    if "recovery_seconds" in ses:
        v = ses["recovery_seconds"]
        if isinstance(v, (int, float)) and 1 <= float(v) <= 120:
            cfg["session"]["recovery_seconds"] = float(v)
        else:
            diagnostics.append("session.recovery_seconds invalid: keeping 5")
    if "fps" in ses:
        if isinstance(ses["fps"], int) and 1 <= ses["fps"] <= 30:
            cfg["session"]["fps"] = ses["fps"]
        else:
            diagnostics.append("session.fps invalid: keeping 12")
    if "paint_budget" in ses:
        if isinstance(ses["paint_budget"], int) and 1000 <= ses["paint_budget"] <= 2000000:
            cfg["session"]["paint_budget"] = ses["paint_budget"]
        else:
            diagnostics.append("session.paint_budget invalid: keeping 200000")
    # bindings ------------------------------------------------------------------
    bnd = data.get("bindings", {})
    if isinstance(bnd, dict):
        seen_keys = {}
        for key, cmd in bnd.items():
            if not isinstance(cmd, str):
                diagnostics.append("bindings[%r] must name a command id" % key)
                continue
            if cmd in EMERGENCY_COMMANDS or key in EMERGENCY_KEYS:
                diagnostics.append("bindings[%r] touches an emergency route: ignored" % key)
                continue
            if key in seen_keys:
                diagnostics.append("bindings[%r] conflicts: keeping first (%r)" % (key, seen_keys[key]))
                continue
            seen_keys[key] = cmd
            cfg["bindings"][key] = cmd
    elif "bindings" in data:
        diagnostics.append("bindings must be a table: ignoring")
    # unknown top-level sections are diagnosed, not fatal
    for key in data:
        if key not in DEFAULT_CONFIG and key != "schema":
            diagnostics.append("unknown config section %r: ignoring" % key)
    return cfg, diagnostics


# --------------------------------------------------------------------------
# themes: md-editor-theme/1.1 subset, skinning-compatible with mdbm.
#
# padsynth tiles reuse mdbm's chrome slots so skins work both ways:
#   pads    -> tile.view.chrome        voice -> tile.edit.chrome
#   browser -> tile.filesystem.chrome  mod   -> tile.contents.chrome
# `tile.<pads|voice|browser|mod>.chrome` aliases are accepted with a
# warning and flagged as a padsynth extension (mdbm would reject them).
# A failed candidate never partially updates the live theme: loading is
# transactional and the caller keeps the previous theme on any error.
# --------------------------------------------------------------------------

THEME_REQUIRED_FALLBACKS = ("ascii", "monochrome", "narrow", "reduced_motion")

THEME_ROOT_FIELDS = {"schema", "id", "name", "description", "extends", "seed", "seed_mode",
                     "fps", "palette", "ramps", "styles", "geometry", "glyphs", "art",
                     "motifs", "patterns", "masks", "layers", "animations", "rules",
                     "variants", "fallbacks"}

PATTERN_KINDS = {"tile", "stripe", "checker", "hatch", "grid", "scanline", "dither",
                 "scatter", "noise", "vignette", "bands", "dropout", "slice-displacement",
                 "fragmentation", "colour-channel-offset", "rails", "ladders",
                 "stepped-path", "brackets", "connectors"}

LAYER_MODES = {"replace", "underlay", "glyph-only", "foreground-only", "background-only",
               "mask", "transparent-cell", "dither-blend"}

LAYER_TRANSFORMS = {"none", "mirror", "rotate90"}

ANIM_PROPS = {"glyph_frame", "style", "palette_phase", "pattern_phase", "offset",
              "density", "mask_threshold", "visibility"}

RULE_SET_FIELDS = {"style", "opacity", "density", "offset", "visible", "phase",
                   "mask_threshold", "palette_phase"}

CANONICAL_SLOTS = {"outer", "divider", "spacer", "tile.filesystem.chrome",
                   "tile.contents.chrome", "tile.edit.chrome", "tile.view.chrome",
                   "behind-content"}

PAD_SLOT_ALIASES = {"tile.pads.chrome": "tile.view.chrome",
                    "tile.voice.chrome": "tile.edit.chrome",
                    "tile.browser.chrome": "tile.filesystem.chrome",
                    "tile.mod.chrome": "tile.contents.chrome"}

TILE_FOR_SLOT = {"tile.view.chrome": "pads", "tile.edit.chrome": "voice",
                 "tile.filesystem.chrome": "browser", "tile.contents.chrome": "mod"}

HOST_CUES = {"startup", "focus-change", "tile-show", "tile-hide", "tile-swap",
             "file-activate", "dirty-change", "save-success", "save-failure",
             "mode-change", "menu-open", "menu-close", "no-context-actions",
             "note-on", "note-off", "audition-start", "audition-stop", "clip-detect",
             "user-1", "user-2", "user-3", "user-4", "user-5", "user-6", "user-7", "user-8"}

LAYER_STATES = {"focused", "active", "previous", "hover", "pressed", "selected",
                "disabled", "dirty", "caution", "destructive", "busy", "success",
                "warning", "error"}

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

MINIMAL_THEME = {
    "schema": THEME_SCHEMA, "id": "minimal", "name": "00 · Minimal (recovery)",
    "description": "Embedded recovery skin. No decoration.",
    "seed": 1, "seed_mode": "fixed", "fps": 2,
    "palette": {"paper": "#000000", "ink": "#e8e8e8", "muted": "#888888",
                "frame": "#444444", "accent": "#ffffff", "code": "#dddddd",
                "link": "#bbbbbb", "violet": "#aaaaaa", "amber": "#ffffff"},
    "styles": {
        "base": {"fg": "ink", "bg": "paper"},
        "accent": {"fg": "accent", "bg": "paper", "bold": True},
        "muted": {"fg": "muted", "bg": "paper"},
        "frame": {"fg": "frame", "bg": "paper"},
    },
    "geometry": {"outer": [0, 0, 0, 0], "border": 1, "divider": 0, "spacer": 0},
    "patterns": {},
    "layers": [],
    "rules": [],
    "animations": [],
    "variants": [],
    "fallbacks": {
        "ascii": {"glyph": "+"},
        "monochrome": {"glyph": "."},
        "narrow": {"glyph": "."},
        "reduced_motion": {"glyph": "."},
    },
}


def _is_hex(value):
    return isinstance(value, str) and bool(HEX_RE.match(value))


def _resolve_palette_color(value, palette, depth=0):
    if depth > 8:
        return None
    if _is_hex(value):
        return value.lower()
    if not isinstance(value, str):
        return None
    if value.startswith("@palette."):
        key = value[len("@palette."):]
        return _resolve_palette_color(palette.get(key), palette, depth + 1)
    if value in palette:
        return _resolve_palette_color(palette[value], palette, depth + 1)
    return None


def _normalize_legacy(data, warnings):
    """Accept schema 1.0's documented subset via the strict normalizer."""
    data = dict(data)
    if "textures" in data:
        if not isinstance(data["textures"], dict):
            return None, ["legacy textures must be a table"]
        patterns = dict(data.get("patterns", {}))
        for key, val in data["textures"].items():
            patterns[key] = val
        data["patterns"] = patterns
        del data["textures"]
        warnings.append("legacy 'textures' normalized to 'patterns'")
    if "panels" in data:
        if not isinstance(data["panels"], list):
            return None, ["legacy panels must be an array"]
        layers = list(data.get("layers", []))
        for panel in data["panels"]:
            layers.append(panel)
        data["layers"] = layers
        del data["panels"]
        warnings.append("legacy 'panels' normalized to 'layers'")
    for name in THEME_REQUIRED_FALLBACKS:
        fb = (data.get("fallbacks") or {})
        if name not in fb:
            data.setdefault("fallbacks", {})[name] = {"glyph": "."}
            warnings.append("legacy theme: conservative fallback '%s' supplied" % name)
    data["schema"] = THEME_SCHEMA
    return data, []


def validate_theme_mapping(data, source="<memory>"):
    """Strict-validate one theme mapping. Returns (errors, warnings, norm|None).

    Unknown fields fail validation. On any error norm is None so callers
    cannot partially apply the candidate.
    """
    errors, warnings = [], []
    if not isinstance(data, dict):
        return ["%s: theme must be a TOML table" % source], warnings, None
    schema = data.get("schema")
    if schema == THEME_SCHEMA_LEGACY:
        data, legacy_errs = _normalize_legacy(data, warnings)
        if data is None:
            return legacy_errs, warnings, None
    elif schema != THEME_SCHEMA:
        return ["%s: schema must be %r" % (source, THEME_SCHEMA)], warnings, None
    for key in data:
        if key.startswith("_"):
            continue  # private runtime meta from a previous load; not schema
        if key not in THEME_ROOT_FIELDS:
            errors.append("%s: unknown root field %r" % (source, key))
    for key in ("id", "name"):
        if not isinstance(data.get(key), str) or not data[key]:
            errors.append("%s: %r must be a non-empty string" % (source, key))
    if "id" in data and (not isinstance(data["id"], str) or not ID_RE.match(data["id"])):
        errors.append("%s: bad theme id %r" % (source, data.get("id")))
    if "extends" in data and data["extends"] is not None:
        ext = data["extends"]
        if isinstance(ext, str):
            ext = [ext]
        if (not isinstance(ext, list) or not ext
                or any(not isinstance(x, str) or not ID_RE.match(x) for x in ext)):
            errors.append("%s: extends must be a theme id or list of ids" % source)
    seed = data.get("seed", 0)
    if "seed" in data and (not isinstance(seed, int) or isinstance(seed, bool)):
        errors.append("%s: seed must be an integer" % source)
    if data.get("seed_mode", "fixed") not in ("fixed", "session", "phased"):
        errors.append("%s: seed_mode must be fixed/session/phased" % source)
    fps = data.get("fps", 12)
    if not isinstance(fps, (int, float)) or not (1 <= float(fps) <= 30):
        errors.append("%s: fps must be 1..30" % source)
    # palette ------------------------------------------------------------
    palette = data.get("palette", {})
    if not isinstance(palette, dict):
        errors.append("%s: palette must be a table" % source)
        palette = {}
    for key, val in palette.items():
        if _resolve_palette_color(val, palette) is None:
            errors.append("%s: palette.%s has bad colour %r" % (source, key, val))
    # ramps ---------------------------------------------------------------
    ramps = data.get("ramps", {})
    if not isinstance(ramps, dict):
        errors.append("%s: ramps must be a table" % source)
        ramps = {}
    for rid, ramp in ramps.items():
        if not ID_RE.match(rid):
            errors.append("%s: bad ramp id %r" % (source, rid))
        if not isinstance(ramp, dict):
            errors.append("%s: ramps.%s must be a table" % (source, rid))
            continue
        for key in ramp:
            if key not in ("colours", "steps"):
                errors.append("%s: ramps.%s unknown field %r" % (source, rid, key))
        colours = ramp.get("colours", [])
        steps = ramp.get("steps", 0)
        if (not isinstance(colours, list) or not (2 <= len(colours) <= 16)
                or any(_resolve_palette_color(c, palette) is None for c in colours)):
            errors.append("%s: ramps.%s needs 2..16 valid colours" % (source, rid))
        if not isinstance(steps, int) or not (2 <= steps <= 256):
            errors.append("%s: ramps.%s steps must be 2..256" % (source, rid))
    # styles ---------------------------------------------------------------
    styles = data.get("styles", {})
    if not isinstance(styles, dict):
        errors.append("%s: styles must be a table" % source)
        styles = {}
    for sid, style in styles.items():
        if not ID_RE.match(sid):
            errors.append("%s: bad style id %r" % (source, sid))
        if not isinstance(style, dict):
            errors.append("%s: styles.%s must be a table" % (source, sid))
            continue
        for key in style:
            if key not in ("fg", "bg", "bold", "italic", "underline", "dim", "strike", "extends"):
                errors.append("%s: styles.%s unknown field %r" % (source, sid, key))
        for ck in ("fg", "bg"):
            if ck in style and _resolve_palette_color(style[ck], palette) is None:
                errors.append("%s: styles.%s.%s bad colour %r" % (source, sid, ck, style[ck]))
        for bk in ("bold", "italic", "underline", "dim", "strike"):
            if bk in style and not isinstance(style[bk], bool):
                errors.append("%s: styles.%s.%s must be boolean" % (source, sid, bk))
    # geometry --------------------------------------------------------------
    geo = data.get("geometry", {})
    if not isinstance(geo, dict):
        errors.append("%s: geometry must be a table" % source)
        geo = {}
    for key in geo:
        if key not in ("outer", "border", "divider", "spacer"):
            errors.append("%s: geometry unknown field %r" % (source, key))
    if "outer" in geo:
        o = geo["outer"]
        if (not isinstance(o, list) or len(o) != 4
                or any(not isinstance(x, int) or not (0 <= x <= 12) for x in o)):
            errors.append("%s: geometry.outer must be 4 ints 0..12" % source)
    for key in ("border", "divider", "spacer"):
        if key in geo and (not isinstance(geo[key], int) or not (0 <= geo[key] <= 4)):
            errors.append("%s: geometry.%s must be 0..4" % (source, key))
    # glyphs / art / motifs ---------------------------------------------------
    for section in ("glyphs", "art", "motifs", "masks"):
        sec = data.get(section, {})
        if sec is None:
            continue
        if not isinstance(sec, dict):
            errors.append("%s: %s must be a table" % (source, section))
    glyphs = data.get("glyphs", {}) or {}
    for gid, glyph in glyphs.items():
        if not ID_RE.match(gid):
            errors.append("%s: bad glyphs id %r" % (source, gid))
        if not isinstance(glyph, dict):
            errors.append("%s: glyphs.%s must be a table" % (source, gid))
            continue
        for key in glyph:
            if key not in ("symbols", "mirror", "rotate90"):
                errors.append("%s: glyphs.%s unknown field %r" % (source, gid, key))
    art = data.get("art", {}) or {}
    for aid, block in art.items():
        if not ID_RE.match(aid):
            errors.append("%s: bad art id %r" % (source, aid))
        if not isinstance(block, dict):
            errors.append("%s: art.%s must be a table" % (source, aid))
            continue
        reps = [k for k in ("rows", "grid", "rle") if k in block]
        if len(reps) != 1:
            errors.append("%s: art.%s needs exactly one of rows/grid/rle" % (source, aid))
        for key in block:
            if key not in ("rows", "grid", "rle", "legend", "style"):
                errors.append("%s: art.%s unknown field %r" % (source, aid, key))
    motifs = data.get("motifs", {}) or {}
    for mid, motif in motifs.items():
        if not ID_RE.match(mid):
            errors.append("%s: bad motif id %r" % (source, mid))
        if not isinstance(motif, dict):
            errors.append("%s: motifs.%s must be a table" % (source, mid))
            continue
        for key in motif:
            if key not in ("art", "pattern", "gap"):
                errors.append("%s: motifs.%s unknown field %r" % (source, mid, key))
        if ("art" in motif) == ("pattern" in motif):
            errors.append("%s: motifs.%s needs exactly one of art/pattern" % (source, mid))
    masks = data.get("masks", {}) or {}
    for mid, mask in masks.items():
        if not ID_RE.match(mid):
            errors.append("%s: bad mask id %r" % (source, mid))
        if not isinstance(mask, dict):
            errors.append("%s: masks.%s must be a table" % (source, mid))
            continue
        for key in mask:
            if key not in ("pattern", "threshold", "invert"):
                errors.append("%s: masks.%s unknown field %r" % (source, mid, key))
        th = mask.get("threshold", 0.5)
        if not isinstance(th, (int, float)) or not (0.0 <= float(th) <= 1.0):
            errors.append("%s: masks.%s threshold must be 0..1" % (source, mid))
    # patterns ------------------------------------------------------------------
    patterns = data.get("patterns", {}) or {}
    for pid, pat in patterns.items():
        if not ID_RE.match(pid):
            errors.append("%s: bad pattern id %r" % (source, pid))
        if not isinstance(pat, dict):
            errors.append("%s: patterns.%s must be a table" % (source, pid))
            continue
        for key in pat:
            if key not in ("kind", "glyphs", "style", "period", "density", "phase", "amplitude"):
                errors.append("%s: patterns.%s unknown field %r" % (source, pid, key))
        if pat.get("kind") not in PATTERN_KINDS:
            errors.append("%s: patterns.%s bad kind %r" % (source, pid, pat.get("kind")))
        if not isinstance(pat.get("glyphs"), list) or not pat["glyphs"]:
            errors.append("%s: patterns.%s needs a glyph list" % (source, pid))
        per = pat.get("period", [8, 4])
        if (not isinstance(per, list) or len(per) != 2
                or any(not isinstance(x, int) or not (1 <= x <= 256) for x in per)):
            errors.append("%s: patterns.%s period must be [1..256, 1..256]" % (source, pid))
        if "density" in pat and (not isinstance(pat["density"], (int, float))
                                 or not (0.0 <= float(pat["density"]) <= 1.0)):
            errors.append("%s: patterns.%s density must be 0..1" % (source, pid))
    # layers ----------------------------------------------------------------------
    layers = data.get("layers", [])
    if not isinstance(layers, list):
        errors.append("%s: layers must be an array" % source)
        layers = []
    layer_ids = set()
    for i, layer in enumerate(layers):
        where = "%s: layers[%d]" % (source, i)
        if not isinstance(layer, dict):
            errors.append("%s must be a table" % where)
            continue
        for key in layer:
            if key not in ("id", "slot", "art", "pattern", "motif", "style", "mode",
                           "offset", "repeat", "opacity", "mask", "visible",
                           "family", "transform"):
                errors.append("%s unknown field %r" % (where, key))
        lid = layer.get("id")
        if not isinstance(lid, str) or not ID_RE.match(lid):
            errors.append("%s bad id %r" % (where, lid))
        elif lid in layer_ids:
            errors.append("%s duplicate layer id %r" % (where, lid))
        else:
            layer_ids.add(lid)
        slot = layer.get("slot")
        if slot in PAD_SLOT_ALIASES:
            warnings.append("%s: slot %r is a padsynth alias for %r" % (where, slot, PAD_SLOT_ALIASES[slot]))
        elif slot not in CANONICAL_SLOTS:
            errors.append("%s bad slot %r" % (where, slot))
        srcs = [k for k in ("art", "pattern", "motif") if k in layer]
        if len(srcs) != 1:
            errors.append("%s needs exactly one of art/pattern/motif" % where)
        if layer.get("mode", "transparent-cell") not in LAYER_MODES:
            errors.append("%s bad mode %r" % (where, layer.get("mode")))
        if "offset" in layer:
            off = layer["offset"]
            if (not isinstance(off, list) or len(off) != 2
                    or any(not isinstance(x, int) for x in off)):
                errors.append("%s offset must be [int, int]" % where)
        if "opacity" in layer and (not isinstance(layer["opacity"], (int, float))
                                   or not (0.0 <= float(layer["opacity"]) <= 1.0)):
            errors.append("%s opacity must be 0..1" % where)
        if "transform" in layer and layer["transform"] not in LAYER_TRANSFORMS:
            errors.append("%s bad transform %r" % (where, layer.get("transform")))
    # rules -------------------------------------------------------------------------
    rules = data.get("rules", [])
    if not isinstance(rules, list):
        errors.append("%s: rules must be an array" % source)
        rules = []
    for i, rule in enumerate(rules):
        where = "%s: rules[%d]" % (source, i)
        if not isinstance(rule, dict):
            errors.append("%s must be a table" % where)
            continue
        for key in rule:
            if key not in ("target", "states", "cue", "set"):
                errors.append("%s unknown field %r" % (where, key))
        target = rule.get("target", "")
        if not (isinstance(target, str) and target.startswith("layer.")
                and target[len("layer."):] in layer_ids):
            errors.append("%s bad target %r (want layer.<id>)" % (where, target))
        if "states" in rule:
            states = rule["states"]
            if not isinstance(states, list) or any(s not in LAYER_STATES for s in states):
                errors.append("%s bad states %r" % (where, states))
        if "cue" in rule and rule["cue"] not in HOST_CUES:
            errors.append("%s bad cue %r" % (where, rule["cue"]))
        setters = rule.get("set", {})
        if not isinstance(setters, dict) or not setters:
            errors.append("%s set must be a non-empty table" % where)
        else:
            for key in setters:
                if key not in RULE_SET_FIELDS:
                    errors.append("%s set unknown field %r" % (where, key))
    # animations ----------------------------------------------------------------------
    anims = data.get("animations", [])
    if not isinstance(anims, list):
        errors.append("%s: animations must be an array" % source)
        anims = []
    if len(anims) > 32:
        errors.append("%s: at most 32 animations (%d given)" % (source, len(anims)))
    for i, anim in enumerate(anims):
        where = "%s: animations[%d]" % (source, i)
        if not isinstance(anim, dict):
            errors.append("%s must be a table" % where)
            continue
        for key in anim:
            if key not in ("id", "target", "property", "values", "duration", "loop", "cue"):
                errors.append("%s unknown field %r" % (where, key))
        if not isinstance(anim.get("id"), str) or not ID_RE.match(anim.get("id", "")):
            errors.append("%s bad id" % where)
        target = anim.get("target", "")
        if not (isinstance(target, str) and target.startswith("layer.")
                and target[len("layer."):] in layer_ids):
            errors.append("%s bad target %r" % (where, target))
        if anim.get("property") not in ANIM_PROPS:
            errors.append("%s bad property %r" % (where, anim.get("property")))
        vals = anim.get("values", [])
        if not isinstance(vals, list) or not (1 <= len(vals) <= 256):
            errors.append("%s values needs 1..256 entries" % where)
        dur = anim.get("duration", 0)
        if not isinstance(dur, (int, float)) or not (0.5 <= float(dur) <= 3600):
            errors.append("%s duration must be 0.5..3600s" % where)
        if "cue" in anim and anim["cue"] not in HOST_CUES:
            errors.append("%s bad cue %r" % (where, anim["cue"]))
    # variants --------------------------------------------------------------------------
    variants = data.get("variants", [])
    if not isinstance(variants, list):
        errors.append("%s: variants must be an array" % source)
        variants = []
    for i, var in enumerate(variants):
        where = "%s: variants[%d]" % (source, i)
        if not isinstance(var, dict):
            errors.append("%s must be a table" % where)
            continue
        for key in var:
            if key not in ("when", "palette", "hide_layers", "show_layers"):
                errors.append("%s unknown field %r" % (where, key))
        when = var.get("when", {})
        if not isinstance(when, dict):
            errors.append("%s when must be a table" % where)
        else:
            for key in when:
                if key not in ("min_width", "max_width", "colour_depth", "unicode",
                               "motion", "high_contrast"):
                    errors.append("%s when unknown condition %r" % (where, key))
    # fallbacks ----------------------------------------------------------------------------
    fallbacks = data.get("fallbacks", {})
    if not isinstance(fallbacks, dict):
        errors.append("%s: fallbacks must be a table" % source)
        fallbacks = {}
    for name in THEME_REQUIRED_FALLBACKS:
        if name not in fallbacks:
            errors.append("%s: missing fallbacks.%s" % (source, name))
    for name, fb in fallbacks.items():
        if not isinstance(fb, dict):
            errors.append("%s: fallbacks.%s must be a table" % (source, name))
            continue
        for key in fb:
            if key not in ("glyph", "hide_layers", "palette"):
                errors.append("%s: fallbacks.%s unknown field %r" % (source, name, key))
    if errors:
        return errors, warnings, None
    norm = dict(data)
    norm["_source"] = source
    norm["_padsynth_extension"] = any(
        isinstance(ly, dict) and ly.get("slot") in PAD_SLOT_ALIASES for ly in layers)
    return [], warnings, norm


def discover_themes(directories, base_dir):
    catalog = {}
    for directory in directories:
        d = directory if os.path.isabs(directory) else os.path.join(base_dir, directory)
        if not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            if not fname.endswith(".theme"):
                continue
            catalog[fname[:-len(".theme")]] = os.path.join(d, fname)
    return catalog


def load_theme_file(path, catalog=None, _chain=()):
    """Transactional load with extends (max 8 ancestors). Never half-applies."""
    if tomllib is None:
        return None, ["tomllib unavailable"], []
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except Exception as exc:
        return None, ["%s: parse failed (%s)" % (path, exc)], []
    errors, warnings, norm = validate_theme_mapping(data, source=path)
    if norm is None:
        return None, errors, warnings
    ancestors = norm.get("extends")
    if ancestors:
        if isinstance(ancestors, str):
            ancestors = [ancestors]
        if len(_chain) + len(ancestors) > 8:
            return None, ["%s: extends chain exceeds 8 ancestors" % path], warnings
        merged = {}
        for parent_id in ancestors:
            if parent_id in _chain or parent_id == norm["id"]:
                return None, ["%s: extends cycle at %r" % (path, parent_id)], warnings
            parent_path = (catalog or {}).get(parent_id)
            if parent_path is None:
                return None, ["%s: unknown ancestor theme %r" % (path, parent_id)], warnings
            parent, perr, pwarn = load_theme_file(parent_path, catalog, _chain + (norm["id"],))
            if parent is None:
                return None, perr, warnings + pwarn
            warnings.extend(pwarn)
            for key, val in parent.items():
                if key.startswith("_"):
                    continue
                if isinstance(val, dict) and isinstance(merged.get(key), dict):
                    merged[key] = dict(val)
                    merged[key].update(merged.get(key, {}))
                elif key not in merged:
                    merged[key] = val
        for key, val in norm.items():
            if key.startswith("_"):
                continue
            if isinstance(val, dict) and isinstance(merged.get(key), dict):
                both = dict(merged[key])
                both.update(val)
                merged[key] = both
            elif isinstance(val, list) and key in ("layers", "animations", "rules", "variants"):
                merged[key] = val  # arrays replace (spec)
            else:
                merged[key] = val
        merged["_source"] = path
        errors2, warnings2, norm2 = validate_theme_mapping(
            {k: v for k, v in merged.items() if not k.startswith("_")}, source=path)
        # reattach schema-adjacent meta then revalidate fully
        if norm2 is None:
            return None, errors2, warnings + warnings2
        warnings.extend(warnings2)
        return norm2, [], warnings
    return norm, [], warnings


def compile_ramps(norm):
    """Deterministic indexed colours for each ramp: {ramp_id: [hex,...]}."""
    palette = norm.get("palette", {})
    out = {}
    for rid, ramp in (norm.get("ramps", {}) or {}).items():
        stops = [_resolve_palette_color(c, palette) for c in ramp["colours"]]
        steps = int(ramp["steps"])
        if len(stops) < 2 or steps < 2:
            continue
        pts = []
        for h in stops:
            pts.append((int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)))
        cols = []
        for s in range(steps):
            pos = s * (len(pts) - 1) / (steps - 1)
            lo = min(len(pts) - 2, int(pos))
            frac = pos - lo
            r = int(pts[lo][0] + (pts[lo + 1][0] - pts[lo][0]) * frac)
            g = int(pts[lo][1] + (pts[lo + 1][1] - pts[lo][1]) * frac)
            b = int(pts[lo][2] + (pts[lo + 1][2] - pts[lo][2]) * frac)
            cols.append("#%02x%02x%02x" % (r, g, b))
        out[rid] = cols
    return out


def theme_style_map(norm):
    """Resolve style extends + palette aliases -> {name: {fg,bg,...}}."""
    palette = norm.get("palette", {})
    styles = norm.get("styles", {})
    resolved = {}

    def resolve(sid, trail=()):
        if sid in resolved:
            return resolved[sid]
        if sid in trail:
            return {"fg": "#ffffff", "bg": "#000000"}
        raw = styles.get(sid, {})
        base = {}
        if "extends" in raw and isinstance(raw["extends"], str) and raw["extends"] in styles:
            base = dict(resolve(raw["extends"], trail + (sid,)))
        merged = dict(base)
        merged.update({k: v for k, v in raw.items() if k != "extends"})
        for ck in ("fg", "bg"):
            if ck in merged:
                merged[ck] = _resolve_palette_color(merged[ck], palette) or "#ffffff"
        resolved[sid] = merged
        return merged

    for sid in styles:
        resolve(sid)
    return resolved


def quantize_hex(hexcol, depth):
    hexcol = hexcol.lower()
    if depth in ("truecolour", "auto"):
        return hexcol
    r, g, b = int(hexcol[1:3], 16), int(hexcol[3:5], 16), int(hexcol[5:7], 16)
    if depth == "mono":
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        return "#ffffff" if lum > 127 else "#000000"
    # 256-colour cube approximation
    def _q(v):
        return min(5, int(round(v / 255.0 * 5.0)))

    return "ansicolor-%d" % (16 + 36 * _q(r) + 6 * _q(g) + _q(b)) if depth == "256" else hexcol


# --------------------------------------------------------------------------
# session state (local, bounded, atomic; plaintext, not encrypted)
# --------------------------------------------------------------------------

def state_dir_for(cfg, cwd=None):
    base = cwd or os.getcwd()
    d = cfg["application"]["state_directory"]
    return d if os.path.isabs(d) else os.path.join(base, d)


def load_session(cfg, cwd=None):
    path = os.path.join(state_dir_for(cfg, cwd), "session.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_session(cfg, payload, cwd=None):
    sdir = state_dir_for(cfg, cwd)
    os.makedirs(sdir, exist_ok=True)
    atomic_write_text(os.path.join(sdir, "session.json"), json.dumps(payload, indent=1))


def probe_state_lock(cfg, cwd=None):
    """Read-only lock probe for diagnostics (never writes)."""
    lock = os.path.join(state_dir_for(cfg, cwd), "lock")
    try:
        if not os.path.isfile(lock):
            return "free"
        with open(lock, "r", encoding="utf-8") as fh:
            other = fh.read().strip()
        age = time.time() - os.path.getmtime(lock)
        if not other or age >= 60.0:
            return "free"
        return "held by pid %s" % other
    except OSError:
        return "unknown"


def check_state_lock(cfg, cwd=None):
    """Second instances cannot take over: returns warning or None."""
    sdir = state_dir_for(cfg, cwd)
    lock = os.path.join(sdir, "lock")
    pid = str(os.getpid())
    try:
        os.makedirs(sdir, exist_ok=True)
        if os.path.isfile(lock):
            with open(lock, "r", encoding="utf-8") as fh:
                other = fh.read().strip()
            if other and other != pid:
                try:
                    age = time.time() - os.path.getmtime(lock)
                except OSError:
                    age = 0.0
                if age < 60.0:
                    return "state locked by pid %s; running read-only on session" % other
                # stale lock from a dead process: take over silently
        atomic_write_text(lock, pid)
    except OSError as exc:
        return "state lock unavailable (%s)" % exc
    return None


# --------------------------------------------------------------------------
# command registry: every mouse action maps to a command id (parity audit)
# --------------------------------------------------------------------------

# Adjustable parameter rows: (row_id, label, node_id, param, step)
PARAM_ROWS = [
    ("osc.detune", "DETUNE c", "osc1", "detune_cents", 1.0),
    ("osc.saw", "SAW mix", "osc1", "saw_mix", 0.05),
    ("osc.pulse", "PULSE mix", "osc1", "pulse_mix", 0.05),
    ("osc.sub", "SUB sine", "osc1", "sub_sine", 0.05),
    ("ens.spread", "STR spread", "ens1", "spread_cents", 1.0),
    ("ens.voices", "STR voices", "ens1", "voices", 1),
    ("air.cutoff", "AIR cutoff", "air1", "cutoff_hz", 500.0),
    ("flt.cutoff", "CUTOFF hz", "filt1", "cutoff_hz", 100.0),
    ("flt.reso", "RESONANCE", "filt1", "resonance", 0.05),
    ("flt.env", "ENV amount", "filt1", "env_amount", 0.1),
    ("env.attack", "ATTACK s", "env1", "attack_s", 0.1),
    ("env.decay", "DECAY s", "env1", "decay_s", 0.2),
    ("env.release", "RELEASE s", "env1", "release_s", 0.2),
    ("lfo1.rate", "LFO1 rate", "lfo1", "rate_hz", 0.01),
    ("mod.cutoff", "MOD cutoff", "route1", "amount", 0.05),
    ("fx.chorus", "CHORUS mix", "ch1", "mix", 0.05),
    ("fx.delay", "DELAY mix", "dly1", "mix", 0.05),
    ("fx.verb", "REVERB mix", "vrb1", "mix", 0.05),
    ("out.gain", "MASTER gain", "out", "gain", 0.05),
    ("out.width", "STEREO width", "out", "width", 0.1),
]

PAD_ROOTS = [33, 36, 38, 40, 41, 43, 45, 47, 48, 50, 52, 55, 57, 60, 64, 67]

# Piano strip geometry (content cells, borders excluded by the toolkit).
PIANO_WHITE_W = 5
PIANO_WHITE_N = 14  # two octaves
PIANO_ROWS = 8
PIANO_SAFE_ROWS = 4  # lowest rows: always 100% velocity
PIANO_SCALE = (0, 2, 4, 5, 7, 9, 11)
PIANO_BLACK_AFTER = (0, 1, 3, 4, 5)  # within-octave white slots followed by a black key
PIANO_LETTERS = ("C", "D", "E", "F", "G", "A", "B")
# tracker keyboard map: key -> semitone offset from piano_base
PIANO_TRACKER = (("z", 0), ("s", 1), ("x", 2), ("d", 3), ("c", 4), ("v", 5),
                 ("g", 6), ("b", 7), ("h", 8), ("n", 9), ("j", 10), ("m", 11))


def piano_white_midi(base, i):
    return int(base) + PIANO_SCALE[i % 7] + 12 * (i // 7)


def piano_key_at(base, x, y):
    """Map piano content coords to (midi, is_black). Black keys live only
    in the upper rows, like a real piano; low clicks always find white."""
    wi = clamp(x // PIANO_WHITE_W, 0, PIANO_WHITE_N - 1)
    bx = x - wi * PIANO_WHITE_W
    if y <= PIANO_ROWS - PIANO_SAFE_ROWS - 1:
        b = None
        if bx == PIANO_WHITE_W - 1 and (wi % 7) in PIANO_BLACK_AFTER:
            b = wi
        elif bx in (0, 1) and wi > 0 and ((wi - 1) % 7) in PIANO_BLACK_AFTER:
            b = wi - 1
        if b is not None:
            return clamp(piano_white_midi(base, b) + 1, 0, 127), True
    return clamp(piano_white_midi(base, wi), 0, 127), False


def piano_velocity(y):
    """Higher click = softer; the lowest PIANO_SAFE_ROWS are always full."""
    if y >= PIANO_ROWS - PIANO_SAFE_ROWS:
        return 1.0
    return clamp(0.3 + 0.7 * (y + 1) / float(PIANO_ROWS - PIANO_SAFE_ROWS),
                 0.05, 1.0)


def pad_chord(pad_index, octave_shift=0):
    root = clamp(PAD_ROOTS[clamp(pad_index, 0, 15)] + 12 * octave_shift, 12, 84)
    tones = [root, root + 7, root + 12, root + 16]
    return [t for t in tones if t <= 96]


COMMANDS = [
    {"id": "palette.open", "title": "Command palette", "keys": ["c-p"], "mouse": None},
    {"id": "ribbon.focus", "title": "Focus ribbon (F10 latch)", "keys": ["f10"], "mouse": None},
    {"id": "help.show", "title": "Help: keys + mouse contract", "keys": ["f1"], "mouse": "click status bar"},
    {"id": "quit.request", "title": "Quit (dirty guard)", "keys": ["c-q"], "mouse": "ribbon HELP > quit"},
    {"id": "layout.restore", "title": "Restore all tiles", "keys": ["c-t"], "mouse": "ribbon TILE > restore"},
    {"id": "tile.next", "title": "Focus next tile", "keys": ["tab"], "mouse": None},
    {"id": "tile.prev", "title": "Focus previous tile", "keys": ["s-tab"], "mouse": None},
    {"id": "tile.focus-1", "title": "Focus browser", "keys": ["esc 1"], "mouse": "click tile"},
    {"id": "tile.focus-2", "title": "Focus pads", "keys": ["esc 2"], "mouse": "click tile"},
    {"id": "tile.focus-3", "title": "Focus voice", "keys": ["esc 3"], "mouse": "click tile"},
    {"id": "tile.focus-4", "title": "Focus mod/fx", "keys": ["esc 4"], "mouse": "click tile"},
    {"id": "tile.focus-5", "title": "Focus piano", "keys": ["esc 5"], "mouse": "click tile"},
    {"id": "piano.key", "title": "Play piano note (offset, vel)", "keys": ["z", "s", "x", "d", "c", "v", "g", "b", "h", "n", "j", "m"], "mouse": "click piano key"},
    {"id": "piano.octave.up", "title": "Piano octave up", "keys": ["."], "mouse": "wheel over piano"},
    {"id": "piano.octave.down", "title": "Piano octave down", "keys": [","], "mouse": "palette"},
    {"id": "patch.new", "title": "New patch (init)", "keys": [], "mouse": "ribbon PATCH > new"},
    {"id": "patch.open", "title": "Open patch", "keys": ["c-o"], "mouse": "browser row click selects, click again opens"},
    {"id": "patch.save", "title": "Save patch", "keys": ["c-s"], "mouse": "ribbon PATCH > save"},
    {"id": "patch.save-as", "title": "Save patch as...", "keys": ["f4"], "mouse": "ribbon PATCH > save as"},
    {"id": "patch.revert", "title": "Revert patch", "keys": [], "mouse": "ribbon PATCH > revert"},
    {"id": "audition.start", "title": "Audition chord", "keys": [" "], "mouse": "AUDITION button"},
    {"id": "audition.stop", "title": "Stop sound", "keys": ["escape"], "mouse": "STOP button"},
    {"id": "drone.toggle", "title": "Drone loop on/off", "keys": ["D"], "mouse": "DRONE toggle"},
    {"id": "demo.medley", "title": "Play demo medley (5 patches)", "keys": [], "mouse": "ribbon HELP > medley"},
    {"id": "panic", "title": "All notes off", "keys": ["c-h"], "mouse": "ribbon VOICE > panic"},
    {"id": "octave.up", "title": "Pad octave up", "keys": ["+"], "mouse": "OCT +/- buttons"},
    {"id": "octave.down", "title": "Pad octave down", "keys": ["-"], "mouse": "OCT +/- buttons"},
    {"id": "velocity.up", "title": "Velocity up", "keys": ["]"], "mouse": "VEL +/- buttons"},
    {"id": "velocity.down", "title": "Velocity down", "keys": ["["], "mouse": "VEL +/- buttons"},
    {"id": "param.next", "title": "Next parameter", "keys": ["down"], "mouse": None},
    {"id": "param.prev", "title": "Previous parameter", "keys": ["up"], "mouse": None},
    {"id": "param.inc", "title": "Parameter +", "keys": ["right"], "mouse": "click slider bar"},
    {"id": "param.dec", "title": "Parameter -", "keys": ["left"], "mouse": "click slider bar"},
    {"id": "param.max", "title": "Parameter to max", "keys": ["end"], "mouse": None},
    {"id": "param.min", "title": "Parameter to min", "keys": ["home"], "mouse": None},
    {"id": "param.reset", "title": "Parameter reset", "keys": ["0"], "mouse": "right-click slider"},
    {"id": "theme.choose", "title": "Theme chooser", "keys": [], "mouse": "browser theme row / status theme"},
    {"id": "theme.next", "title": "Next theme", "keys": ["f8"], "mouse": "ribbon THEME > next"},
    {"id": "theme.prev", "title": "Previous theme", "keys": ["M"], "mouse": "ribbon THEME > prev"},
    {"id": "motion.cycle", "title": "Motion off/reduced/normal/high", "keys": ["o"], "mouse": "ribbon THEME > motion"},
    {"id": "immersive.toggle", "title": "Immersive art on/off", "keys": ["i"], "mouse": "ribbon THEME > immersive"},
    {"id": "tile.toggle-pads", "title": "Show/hide pads", "keys": [], "mouse": "ribbon HELP menu / palette"},
    {"id": "tile.toggle-voice", "title": "Show/hide voice", "keys": [], "mouse": "ribbon HELP menu / palette"},
    {"id": "tile.toggle-mod", "title": "Show/hide mod", "keys": [], "mouse": "ribbon HELP menu / palette"},
    {"id": "tile.toggle-browser", "title": "Show/hide browser", "keys": [], "mouse": "ribbon HELP menu / palette"},
    {"id": "tile.toggle-piano", "title": "Show/hide piano", "keys": [], "mouse": "ribbon HELP menu / palette"},
    {"id": "divider.left.inc", "title": "Browser divider +", "keys": [">"], "mouse": "click divider right half"},
    {"id": "divider.left.dec", "title": "Browser divider -", "keys": ["<"], "mouse": "click divider left half"},
    {"id": "divider.center.inc", "title": "Pads divider +", "keys": ["}"], "mouse": "click divider right half"},
    {"id": "divider.center.dec", "title": "Pads divider -", "keys": ["{"], "mouse": "click divider left half"},
    {"id": "render.wav", "title": "Render patch to WAV", "keys": ["c-r"], "mouse": "ribbon PATCH > render wav"},
    {"id": "diagnostics.show", "title": "Diagnostics overlay", "keys": ["f9"], "mouse": "ribbon HELP > diagnostics"},
    {"id": "menu.open", "title": "Tile menu", "keys": ["esc m"], "mouse": "right-click tile content"},
    {"id": "overlay.dismiss", "title": "Dismiss one overlay", "keys": ["escape"], "mouse": "outside-click (consumed)"},
    {"id": "browser.scroll-up", "title": "Browser scroll up", "keys": ["pageup"], "mouse": "wheel over browser"},
    {"id": "browser.scroll-down", "title": "Browser scroll down", "keys": ["pagedown"], "mouse": "wheel over browser"},
]

for _i in range(16):
    _keys = [str((_i + 1) % 10)] if _i < 10 else ([chr(ord("a") + _i - 10)] if _i < 16 else [])
    COMMANDS.append({"id": "pad.trigger-%02d" % (_i + 1), "title": "Trigger pad %02d" % (_i + 1),
                     "keys": _keys, "mouse": "click pad cell (x = velocity)"})

MOUSE_ACTIONS = [
    ("pad cell click", "pad.trigger-NN"),
    ("pad velocity by click-x", "pad.trigger-NN"),
    ("slider bar click", "param.inc"),
    ("slider right-click reset", "param.reset"),
    ("tile click focuses + acts", "tile.focus-N"),
    ("browser row click select / again opens", "patch.open"),
    ("browser theme row activate", "theme.choose"),
    ("divider click halves", "divider.left.inc"),
    ("ribbon button", "ribbon.focus"),
    ("menu item", "menu.open"),
    ("outside-click dismiss", "overlay.dismiss"),
    ("wheel scroll tile", "browser.scroll-up"),
    ("AUDITION/STOP/DRONE buttons", "audition.start"),
    ("OCT/VEL buttons", "octave.up"),
    ("ribbon HELP tile toggles", "tile.toggle-pads"),
    ("status bar click", "help.show"),
    ("piano key click", "piano.key"),
    ("piano velocity by click height", "piano.key"),
]


def parity_report():
    """Every mouse action must map to a command id (prefix match allowed)."""
    ids = {c["id"] for c in COMMANDS}
    issues = []

    def known(target):
        if target in ids:
            return True
        return any(cid.startswith(target.rstrip("N").rstrip("-")) for cid in ids)

    for area, target in MOUSE_ACTIONS:
        base = target
        if "NN" in base:
            base = "pad.trigger-01"
        elif base.endswith("-N"):
            base = base[:-2] + "-1"
        if base not in ids and not known(base):
            issues.append("mouse action %r has no command (%s)" % (area, target))
    # every command reachable: palette covers all by construction; check keys/ids sane
    for cmd in COMMANDS:
        if not cmd["id"] or not cmd["title"]:
            issues.append("command with missing id/title: %r" % (cmd,))
    return issues


# --------------------------------------------------------------------------
# text snapshot (no TTY needed; deterministic structural preview)
# --------------------------------------------------------------------------

def level_glyph(frac, ascii_only=False):
    frac = clamp(float(frac), 0.0, 1.0)
    if ascii_only:
        chars = " .:-=+*#%@"
        return chars[min(len(chars) - 1, int(frac * len(chars)))]
    idx = min(len(GLYPH_DENSITY) - 1, int(frac * len(GLYPH_DENSITY)))
    return GLYPH_DENSITY[idx]


def render_snapshot_text(patch, theme, width, height, seed=7, ascii_only=False):
    width = clamp(int(width), 24, 200)
    height = clamp(int(height), 10, 60)
    lines = []
    pname = str(patch.get("name", patch.get("id", "?")))[: width - 24]
    tname = str(theme.get("id", "?")) if isinstance(theme, dict) else "?"
    lines.append(("PADSYNTH /// " + pname.upper() + " /// " + tname)[:width].ljust(width))
    lines.append(("[ PADS / STRINGS / AIR / AMBIENCE /// FIXED VOICES ]")[:width].ljust(width))
    lines.append(("-" * width)[:width])
    # one real micro-render of the audition chord; 16 sequential block peaks
    try:
        rl, rr = render_patch(patch, make_chord(AUDITION_CHORD, 0.6), 0.6, sr=8000, seed=seed)
        mono = [(a + b) * 0.5 for a, b in zip(rl, rr)]
    except Exception:
        mono = [0.0] * 4800
    blocks = 16
    peaks = []
    chunk = max(1, len(mono) // blocks)
    for b in range(blocks):
        seg = mono[b * chunk:(b + 1) * chunk]
        peaks.append(max([abs(v) for v in seg] + [0.0]))
    peak_max = max(peaks + [1e-6])
    for row in range(4):
        cells = []
        for col in range(4):
            v = peaks[row * 4 + col] / peak_max
            g = level_glyph(v, ascii_only)
            cells.append("[%s]" % g)
        lines.append((" ".join(cells) + "  PADS %d-%d" % (row * 4 + 1, row * 4 + 4))[:width].ljust(width))
    lines.append(("-" * width)[:width])
    nodemap = patch_node_map(patch)
    filt = nodemap.get("filt1", {}).get("params", {})
    cutoff = float(filt.get("cutoff_hz", 2200.0))
    norm_cut = clamp(math.log10(max(40.0, cutoff) / 40.0) / math.log10(18000.0 / 40.0), 0.0, 1.0)
    bar_w = max(8, width - 22)
    bar = "#" * int(norm_cut * bar_w) + "." * (bar_w - int(norm_cut * bar_w))
    lines.append(("CUTOFF %5d hz [%s]" % (int(cutoff), bar))[:width].ljust(width))
    env = nodemap.get("env1", {}).get("params", {})
    lines.append(("ENV A %.1f D %.1f S %.2f R %.1f" % (
        float(env.get("attack_s", 1.0)), float(env.get("decay_s", 2.0)),
        float(env.get("sustain", 0.75)), float(env.get("release_s", 3.0))))[:width].ljust(width))
    vrb = nodemap.get("vrb1", {}).get("params", {})
    lines.append(("AIR/VERB mix %.2f size %.2f" % (
        float(vrb.get("mix", 0.4)), float(vrb.get("size", 0.7))))[:width].ljust(width))
    filler = "[%s]" % (("%s structural preview" % patch.get("id", "?")).ljust(width - 2),)
    while len(lines) < height - 1:
        lines.append(filler[:width].ljust(width))
    lines.append(("LIVE / FIXED VOICES // NOTHING MOVED // EVERY PARAM NEGOTIABLE")[:width].ljust(width))
    return "\n".join(lines[:height])


# --------------------------------------------------------------------------
# CLI (non-interactive paths need stdlib only)
# --------------------------------------------------------------------------

def app_base_dir():
    return os.path.dirname(os.path.abspath(__file__))


def default_config_path(base=None):
    return os.path.join(base or app_base_dir(), "padsynth.conf")


def load_patch_file(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            patch = json.load(fh)
    except (OSError, ValueError) as exc:
        return None, ["%s: cannot load (%s)" % (path, exc)]
    errors = validate_patch(patch)
    return patch, errors


def list_patch_files(patch_dir):
    out = []
    if os.path.isdir(patch_dir):
        for fname in sorted(os.listdir(patch_dir)):
            if fname.endswith(".json"):
                out.append(os.path.join(patch_dir, fname))
    return out


def resolve_patch(source, patch_dir):
    if source and os.path.isfile(source):
        return load_patch_file(source)
    if source:
        cand = os.path.join(patch_dir, source if source.endswith(".json") else source + ".json")
        if os.path.isfile(cand):
            return load_patch_file(cand)
        return None, ["unknown patch %r" % source]
    import copy
    return copy.deepcopy(DEFAULT_PATCH), []


# --------------------------------------------------------------------------
# demo mode: a scripted five-patch medley tour (the DashMinimix -Demo
# equivalent: one switch that shows and plays what the app can do)
# --------------------------------------------------------------------------

DEMO_SEQUENCE = [
    ("weather-machine", [45, 52, 57, 60, 64], "Am add9 compound pad"),
    ("needle-rain", [41, 48, 53, 57, 60], "bright pluck over F"),
    ("ion-cell", [43, 50, 55, 59, 62], "narrow cellular pressure"),
    ("cyan-fog", [48, 55, 60, 64, 67], "cold haze, huge space"),
    ("amber-strike", [45, 52, 57, 60, 64], "alert peak, back home"),
]


def build_medley(patch_dir, sr=44100, seed=7, seconds_each=1.8, fade_s=0.15,
                 progress=None):
    """Render one chord per factory patch, joined with equal-power crossfades.

    Returns (stereo, sr, manifest) where manifest lists
    (patch_id, blurb, peak) per segment. Deterministic for fixed inputs.
    progress, when given, is called as progress(done, total, patch_id).
    """
    sr = int(clamp(int(sr), 4000, 96000))
    seconds_each = clamp(float(seconds_each), 0.4, 8.0)
    fade_n = max(1, int(sr * clamp(float(fade_s), 0.02, 1.0)))
    segs = []
    manifest = []
    total = len(DEMO_SEQUENCE)
    for n, (pid, midis, blurb) in enumerate(DEMO_SEQUENCE):
        patch, errs = resolve_patch(pid, patch_dir)
        if patch is None:
            raise ValueError("demo patch %r unavailable: %s" % (pid, "; ".join(errs[:2])))
        seg = render_patch(patch, make_chord(midis, seconds_each), seconds_each, sr, seed)
        manifest.append((pid, blurb, round(buffer_peak(seg), 3)))
        segs.append(seg)
        if progress is not None:
            progress(n + 1, total, pid)
    left = list(segs[0][0])
    right = list(segs[0][1])
    for seg_l, seg_r in [(s[0], s[1]) for s in segs[1:]]:
        n_fade = min(fade_n, len(left), len(seg_l))
        for i in range(n_fade):
            k = float(i) / float(n_fade)
            g_out = math.cos(k * math.pi / 2.0)
            g_in = math.sin(k * math.pi / 2.0)
            j = len(left) - n_fade + i
            left[j] = left[j] * g_out + seg_l[i] * g_in
            right[j] = right[j] * g_out + seg_r[i] * g_in
        left.extend(seg_l[n_fade:])
        right.extend(seg_r[n_fade:])
    peak = buffer_peak((left, right))
    if peak > 0.95:
        k = 0.95 / peak
        left = [v * k for v in left]
        right = [v * k for v in right]
    return (left, right), sr, manifest


def run_demo_text(patch_dir, sr, seed, dest_path, master_gain, progress=None):
    """Render the medley to disk. Returns (stereo, path, seconds, peak, manifest)."""
    stereo, sr, manifest = build_medley(patch_dir, sr, seed, progress=progress)
    g = clamp(float(master_gain), 0.0, 1.5)
    if g != 1.0:
        stereo = ([clamp(v * g, -1.0, 1.0) for v in stereo[0]],
                  [clamp(v * g, -1.0, 1.0) for v in stereo[1]])
    write_wav(dest_path, stereo, sr)
    seconds = len(stereo[0]) / float(sr)
    return stereo, dest_path, seconds, buffer_peak(stereo), manifest


def build_diagnostics(cfg, cfg_diags, theme, theme_warn, patch, patch_errs, backend, lock_warn):
    import shutil
    cols, rows = shutil.get_terminal_size(fallback=(80, 24))
    try:
        import importlib.util
        if importlib.util.find_spec("prompt_toolkit") is None:
            pt = "missing (pip install -r requirements.txt)"
        else:
            import prompt_toolkit as _pt
            pt = "present (%s)" % getattr(_pt, "__version__", "?")
    except Exception as exc:
        pt = "broken (%s)" % exc
    lines = []
    lines.append("padsynth %s // diagnostics" % APP_VERSION)
    lines.append("python %s" % sys.version.split()[0])
    lines.append("tui toolkit: prompt_toolkit %s" % pt)
    lines.append("terminal %dx%d unicode=%s mouse=%s colour=%s" % (
        cols, rows, cfg["capabilities"]["unicode"], cfg["capabilities"]["mouse"],
        cfg["capabilities"]["colour_depth"]))
    lines.append("audio backend=%s (%s)" % (backend[0], backend[1]))
    lines.append("config issues: %d" % len(cfg_diags))
    lines.extend("  config: %s" % d for d in cfg_diags[:12])
    lines.append("theme: %s (warnings %d)" % (theme.get("id", "?") if theme else "NONE", len(theme_warn)))
    lines.extend("  theme: %s" % w for w in theme_warn[:8])
    lines.append("patch: %s (errors %d)" % (patch.get("id", "?") if patch else "NONE", len(patch_errs)))
    lines.extend("  patch: %s" % e for e in patch_errs[:8])
    par = parity_report()
    lines.append("mouse/keyboard parity issues: %d" % len(par))
    lines.extend("  parity: %s" % p for p in par[:8])
    if lock_warn:
        lines.append("session: %s" % lock_warn)
    else:
        lines.append("session: lock ok")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="padsynth",
                                 description="pads/strings/air/ambience TUI synthesiser")
    ap.add_argument("patch", nargs="?", default=None, help="patch id or .json path")
    ap.add_argument("--config", default=None)
    ap.add_argument("--patch-dir", default=None)
    ap.add_argument("--theme", default=None)
    ap.add_argument("--list-themes", action="store_true")
    ap.add_argument("--list-patches", action="store_true")
    ap.add_argument("--validate-theme", default=None, metavar="FILE")
    ap.add_argument("--diagnostics", action="store_true")
    ap.add_argument("--snapshot", default=None, metavar="WxH")
    ap.add_argument("--render", default=None, metavar="OUT.wav")
    ap.add_argument("--demo", action="store_true",
                    help="scripted tour: print it and render demo-medley.wav")
    ap.add_argument("--demo-play", action="store_true",
                    help="demo tour, then play the medley through the audio backend")
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--notes", default=None, help="comma list: 48,C3,Eb4,...")
    ap.add_argument("--sr", type=int, default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--safe-theme", action="store_true")
    ap.add_argument("--no-restore", action="store_true")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    base = app_base_dir()
    cfg_path = args.config or default_config_path(base)
    cfg, cfg_diags = load_config(cfg_path)
    patch_dir = args.patch_dir or os.path.join(base, "patches")
    catalog = discover_themes(cfg["appearance"]["theme_directories"], base)

    if args.list_themes:
        for tid in sorted(catalog):
            print(tid)
        return 0
    if args.list_patches:
        for path in list_patch_files(patch_dir):
            print(os.path.basename(path)[:-5])
        print("weather-machine (built-in)")
        return 0
    if args.validate_theme:
        norm, errs, warns = load_theme_file(args.validate_theme, catalog)
        for w in warns:
            print("warning: %s" % w)
        if norm is None:
            for e in errs:
                print("error: %s" % e)
            return 2
        print("theme %s valid (%d warnings)" % (norm["id"], len(warns)))
        return 0

    patch, patch_errs = resolve_patch(args.patch, patch_dir)
    if patch is None:
        for e in patch_errs:
            print("error: %s" % e)
        return 2

    # theme selection: explicit > session > config > minimal
    theme_id = args.theme
    sess = {} if args.no_restore else (load_session(cfg) if cfg["session"]["restore"] else {})
    if not theme_id:
        theme_id = sess.get("theme") or cfg["appearance"]["theme"]
    if args.safe_theme:
        theme = dict(MINIMAL_THEME)
        theme_warn: list = []
    else:
        theme_path = catalog.get(theme_id)
        if theme_path is None:
            print("warning: unknown theme %r, using minimal" % theme_id)
            theme, theme_warn = dict(MINIMAL_THEME), []
            theme_id = "minimal"
        else:
            loaded, errs, warns = load_theme_file(theme_path, catalog)
            if loaded is None:
                print("warning: theme %r failed, using minimal:" % theme_id)
                for e in errs:
                    print("  error: %s" % e)
                theme, theme_warn = dict(MINIMAL_THEME), []
                theme_id = "minimal"
            else:
                theme, theme_warn = loaded, warns

    seed = cfg["appearance"]["seed"]
    if seed < 0:
        seed = int(theme.get("seed", 7)) if isinstance(theme.get("seed"), int) else 7
    if args.seed is not None:
        seed = args.seed
    sr = args.sr or cfg["audio"]["sample_rate"]
    backend = probe_audio(cfg["audio"]["device"])
    _audio_state["backend"] = backend[0]
    _audio_state["detail"] = backend[1]

    if args.diagnostics:
        probe = probe_state_lock(cfg)
        if probe == "free":
            lock_note = None
        elif probe == "unknown":
            lock_note = "lock status unknown"
        else:
            lock_note = "lock " + probe
        print(build_diagnostics(cfg, cfg_diags, theme, theme_warn, patch, patch_errs,
                                backend, lock_note))
        return 0
    if args.snapshot:
        m = re.fullmatch(r"(\d{2,3})x(\d{2,3})", args.snapshot)
        if not m:
            print("error: --snapshot wants WxH like 100x28")
            return 2
        ascii_only = cfg["accessibility"]["ascii_only"]
        print(render_snapshot_text(patch, theme, int(m.group(1)), int(m.group(2)),
                                   seed=seed, ascii_only=ascii_only))
        return 0
    if args.render:
        seconds = args.seconds or cfg["audio"]["audition_seconds"]
        if args.notes:
            try:
                midis = [note_to_midi(tok) for tok in args.notes.split(",")]
            except ValueError as exc:
                print("error: %s" % exc)
                return 2
            notes = make_chord(midis, seconds)
        else:
            notes = make_chord(AUDITION_CHORD, seconds)
        if patch_errs:
            for e in patch_errs:
                print("error: %s" % e)
            return 2
        stereo = render_patch(patch, notes, seconds, sr, seed)
        g = cfg["audio"]["master_gain"]
        if g != 1.0:
            stereo = ([clamp(v * g, -1.0, 1.0) for v in stereo[0]],
                      [clamp(v * g, -1.0, 1.0) for v in stereo[1]])
        write_wav(args.render, stereo, sr)
        print("rendered %s (%s Hz, peak %.3f)" % (args.render, sr, buffer_peak(stereo)))
        return 0
    if args.demo or args.demo_play:
        dest = os.path.join(os.getcwd(), "demo-medley.wav")

        def _prog(done, total, pid):
            print("demo render %d/%d %s ..." % (done, total, pid))

        try:
            stereo, _dest, seconds, peak, manifest = run_demo_text(
                patch_dir, sr, seed, dest, cfg["audio"]["master_gain"],
                progress=_prog)
        except ValueError as exc:
            print("error: %s" % exc)
            return 2
        print("PADSYNTH DEMO // five patches, one progression")
        for pid, blurb, pk in manifest:
            print("  %-15s %-28s peak %.3f" % (pid, blurb, pk))
        print("rendered %s (%s Hz, %.1f s, peak %.3f)" % (dest, sr, seconds, peak))
        print("launch the TUI: 0Start.cmd (Windows Terminal)")
        print("keys: 1-9 pads · SPACE audition · CTRL+P palette · F1 help")
        if args.demo_play:
            if backend[0] == "null":
                print("no audio backend: playing is unavailable, WAV above is the demo")
                return 0
            play_buffer_async(stereo, sr, backend[0])
            try:
                waited = 0.0
                while _audio_state["playing"] and waited < seconds + 5.0:
                    time.sleep(0.1)
                    waited += 0.1
            except KeyboardInterrupt:
                stop_playback()
        return 0

    # interactive TUI -------------------------------------------------------
    if patch_errs:
        print("patch has errors; opening read-only-ish with diagnostics:")
        for e in patch_errs[:6]:
            print("  error: %s" % e)
    lock_warn = check_state_lock(cfg)
    run_tui(cfg, cfg_diags, patch, args.patch, theme, theme_id, catalog, patch_dir,
            seed, sr, backend, lock_warn, sess, args)
    return 0


# --------------------------------------------------------------------------
# interactive TUI (prompt_toolkit; mouse-first, keyboard-complete)
#
# Parity rule: every mouse gesture calls run_command(), and every command
# is reachable from the palette + a documented key. Dividers step on click
# and step identically on keys. Theme preview is transactional.
# Ambient animation tracks are parsed and validated but only event-driven
# repaints are implemented in 0.1.0 (no timer loop); style/palette tracks
# are therefore trivially within the 2 Hz cap. This gap is documented in
# --diagnostics and the help overlay rather than claimed away.
# --------------------------------------------------------------------------

RIBBON_MENUS = [
    ("PATCH", ["patch.new", "patch.open", "patch.save", "patch.save-as",
               "patch.revert", "render.wav", "audition.start", "audition.stop"]),
    ("VOICE", ["octave.up", "octave.down", "velocity.up", "velocity.down",
               "param.reset", "panic"]),
    ("MOD", ["motion.cycle", "drone.toggle", "param.next", "param.prev"]),
    ("FX", ["param.inc", "param.dec", "diagnostics.show"]),
    ("THEME", ["theme.choose", "theme.next", "theme.prev", "motion.cycle",
               "immersive.toggle"]),
    ("HELP", ["help.show", "diagnostics.show", "demo.medley", "palette.open", "layout.restore",
              "tile.toggle-pads", "tile.toggle-voice", "tile.toggle-mod",
              "tile.toggle-browser", "tile.toggle-piano", "quit.request"]),
]

BAR_COL, BAR_W = 16, 24


class TuiState:
    def __init__(self, cfg, patch, patch_path, theme, theme_id, catalog,
                 patch_dir, seed, sr, backend, sess):
        import copy
        self.cfg = cfg
        self.patch = copy.deepcopy(patch)
        self.patch_path = patch_path
        self.dirty = False
        self.theme = theme
        self.theme_id = theme_id
        self.theme_backup = None
        self.catalog = catalog
        self.patch_dir = patch_dir
        self.seed = seed
        self.sr = sr
        self.backend = backend  # (name, detail)
        self.octave = 0
        self.vel = 0.8
        self.drone = False
        self.piano_base = 60  # MIDI of the leftmost piano white key (C4)
        self.piano_hot = {}  # midi -> time.time() of last trigger (hot flash)
        self.focus_tile = "pads"
        self.hidden = set()
        for key, tile in (("pads_visible", "pads"), ("voice_visible", "voice"),
                          ("mod_visible", "mod"), ("browser_visible", "browser"),
                          ("piano_visible", "piano")):
            if not cfg["layout"].get(key, True):
                self.hidden.add(tile)
        if len(self.hidden) >= 5:
            self.hidden = set()
            self.focus_tile = "pads"
        elif self.focus_tile in self.hidden:
            self.focus_tile = next((t for t in ("pads", "browser", "voice", "mod", "piano")
                                    if t not in self.hidden), "pads")
        self.ratios = {"left": float(cfg["layout"]["left_ratio"]),
                       "center": float(cfg["layout"]["center_ratio"]),
                       "voice": float(cfg["layout"]["voice_ratio"])}
        self.overlay = None  # None|palette|menu|ribbon|help|diag|theme|confirm|input
        self.menu_for = "PATCH"
        self.palette_filter = ""
        self.palette_sel = 0
        self.browser_sel = 0
        self.param_sel = 0
        self.pad_cursor = 0
        self.ribbon_sel = 0
        self.help_scroll = 0
        self.input_title = ""
        self.input_text = ""
        self.input_accept = None
        self.message = "SPACE audition · F10 menus · CTRL+P palette · F1 help"
        self.lock_warn = None
        self.audio_notify = None
        self.fingerprint = self._fingerprint()
        if isinstance(sess, dict):
            try:
                if "ratios" in sess and isinstance(sess["ratios"], dict):
                    for k in self.ratios:
                        if k in sess["ratios"]:
                            self.ratios[k] = clamp(float(sess["ratios"][k]), 0.1, 0.8)
                if "octave" in sess:
                    self.octave = clamp(int(sess["octave"]), -2, 2)
                if "piano_base" in sess:
                    self.piano_base = clamp(int(sess["piano_base"]), 24, 72)
            except (TypeError, ValueError):
                pass

    def _fingerprint(self):
        return hashlib.md5(json.dumps(self.patch, sort_keys=True).encode()).hexdigest()[:12]


def _row_info(patch, row_id):
    for rid, _label, nid, param, step in PARAM_ROWS:
        if rid == row_id:
            node = patch_node_map(patch).get(nid)
            if node is None:
                return None
            spec = PARAM_SPECS.get(param)
            if spec is None:
                return None
            kind, lo, hi, _choices = spec
            scale = "log" if param == "cutoff_hz" else "lin"
            return {"node": nid, "param": param, "step": step, "kind": kind,
                    "lo": lo, "hi": hi, "scale": scale}
    return None


def _get_param(patch, row_id):
    info = _row_info(patch, row_id)
    if info is None:
        return None
    node = patch_node_map(patch)[info["node"]]
    return node.get("params", {}).get(info["param"])


def _set_param(patch, row_id, value):
    info = _row_info(patch, row_id)
    if info is None:
        return "no such parameter (patch lacks the node)"
    kind, lo, hi = info["kind"], info["lo"], info["hi"]
    if kind == "int":
        value = clamp(int(round(value)), lo, hi)
    else:
        value = clamp(float(value), lo, hi)
    patch_node_map(patch)[info["node"]].setdefault("params", {})[info["param"]] = value
    return None


def _frac_to_value(info, frac):
    frac = clamp(float(frac), 0.0, 1.0)
    if info["scale"] == "log":
        lo, hi = math.log10(info["lo"]), math.log10(info["hi"])
        return 10.0 ** (lo + (hi - lo) * frac)
    return info["lo"] + (info["hi"] - info["lo"]) * frac


def _value_to_frac(info, value):
    if info["scale"] == "log":
        lo, hi = math.log10(info["lo"]), math.log10(info["hi"])
        return clamp((math.log10(max(info["lo"], value)) - lo) / (hi - lo), 0.0, 1.0)
    return clamp((value - info["lo"]) / (info["hi"] - info["lo"]), 0.0, 1.0)


def _browser_entries(state):
    entries = []
    for path in list_patch_files(state.patch_dir):
        pid = os.path.basename(path)[:-5]
        entries.append(("patch", pid, path))
    entries.append(("patch", "weather-machine (built-in)", None))
    for tid in sorted(state.catalog):
        entries.append(("theme", tid, state.catalog[tid]))
    return entries


def _filtered_commands(state):
    f = state.palette_filter.lower()
    return [c for c in COMMANDS if f in c["id"].lower() or f in c["title"].lower()]


def run_command(state, cmd_id, arg=None):
    """Execute a command id. Returns a status message. All input routes here."""
    import copy
    st = state
    cmds = {c["id"] for c in COMMANDS}
    if cmd_id.startswith("pad.trigger-"):
        try:
            idx = int(cmd_id.rsplit("-", 1)[1]) - 1
        except ValueError:
            return "bad pad id"
        vel = float(arg) if arg is not None else st.vel
        chord = pad_chord(idx, st.octave)
        notes = make_chord(chord, st.cfg["audio"]["audition_seconds"], vel)
        try:
            audition_async(st.patch, notes, st.cfg["audio"]["audition_seconds"],
                           st.sr, st.seed, st.backend[0], loop=False,
                           notify=getattr(st, "audio_notify", None))
        except Exception as exc:
            return "audition failed: %s" % exc
        st.pad_cursor = idx
        return "pad %02d [%s] vel %.2f" % (idx + 1, ",".join(midi_to_name(m) for m in chord), vel)
    if cmd_id == "audition.start":
        notes = make_chord(AUDITION_CHORD, st.cfg["audio"]["audition_seconds"], st.vel)
        try:
            audition_async(st.patch, notes, st.cfg["audio"]["audition_seconds"],
                           st.sr, st.seed, st.backend[0], loop=False,
                           notify=getattr(st, "audio_notify", None))
        except Exception as exc:
            return "audition failed: %s" % exc
        return "rendering audition via %s ..." % st.backend[0]
    if cmd_id == "audition.stop":
        stop_playback()
        st.drone = False
        return "stopped"
    if cmd_id == "panic":
        stop_playback()
        st.drone = False
        return "all notes off"
    if cmd_id == "drone.toggle":
        st.drone = not st.drone
        if st.drone:
            notes = make_chord(AUDITION_CHORD, 4.0, st.vel)
            try:
                audition_async(st.patch, notes, 4.0, st.sr, st.seed, st.backend[0], loop=True,
                               notify=getattr(st, "audio_notify", None))
            except Exception as exc:
                st.drone = False
                return "drone failed: %s" % exc
            return "drone on (%s)" % st.backend[0]
        stop_playback()
        return "drone off"
    if cmd_id == "piano.key":
        off, vel = 0, None
        if isinstance(arg, (tuple, list)) and len(arg) == 2:
            off, vel = arg
        elif isinstance(arg, (int, float)) and not isinstance(arg, bool):
            off = arg
        try:
            off = int(off)
        except (TypeError, ValueError):
            off = 0
        midi = clamp(int(st.piano_base) + off, 0, 127)
        vel = st.vel if vel is None else clamp(float(vel), 0.05, 1.0)
        secs = float(st.cfg["audio"]["audition_seconds"])
        try:
            audition_async(st.patch, make_chord([midi], secs, vel), secs,
                           st.sr, st.seed, st.backend[0], loop=False,
                           notify=getattr(st, "audio_notify", None))
        except Exception as exc:
            return "piano failed: %s" % exc
        now = time.time()
        st.piano_hot[midi] = now
        for k in [k for k, v in st.piano_hot.items() if now - v > 1.0]:
            del st.piano_hot[k]
        return "%s vel %.2f" % (midi_to_name(midi), vel)
    if cmd_id == "piano.octave.up":
        st.piano_base = clamp(st.piano_base + 12, 24, 72)
        return "piano %s" % midi_to_name(st.piano_base)
    if cmd_id == "piano.octave.down":
        st.piano_base = clamp(st.piano_base - 12, 24, 72)
        return "piano %s" % midi_to_name(st.piano_base)
    if cmd_id == "demo.medley":
        st.overlay = None
        notify = getattr(st, "audio_notify", None)

        def _build_and_play():
            try:
                stereo, _sr, _manifest = build_medley(st.patch_dir, st.sr, st.seed)
                play_buffer_async(stereo, _sr, st.backend[0], notify=notify)
            except Exception as exc:
                _audio_state["error"] = str(exc)
                if notify is not None:
                    try:
                        notify()
                    except Exception:
                        pass

        threading.Thread(target=_build_and_play, daemon=True).start()
        return "rendering demo medley (5 patches) ..."
    if cmd_id == "octave.up":
        st.octave = clamp(st.octave + 1, -2, 2)
        return "pad octave %+d" % st.octave
    if cmd_id == "octave.down":
        st.octave = clamp(st.octave - 1, -2, 2)
        return "pad octave %+d" % st.octave
    if cmd_id == "velocity.up":
        st.vel = clamp(round(st.vel + 0.05, 2), 0.1, 1.0)
        return "velocity %.2f" % st.vel
    if cmd_id == "velocity.down":
        st.vel = clamp(round(st.vel - 0.05, 2), 0.1, 1.0)
        return "velocity %.2f" % st.vel
    if cmd_id in ("param.next", "param.prev"):
        d = 1 if cmd_id == "param.next" else -1
        st.param_sel = (st.param_sel + d) % len(PARAM_ROWS)
        return PARAM_ROWS[st.param_sel][1]
    if cmd_id in ("param.inc", "param.dec", "param.max", "param.min", "param.reset"):
        rid = PARAM_ROWS[st.param_sel][0]
        info = _row_info(st.patch, rid)
        if info is None:
            return "parameter unavailable in this patch"
        cur = _get_param(st.patch, rid)
        if cmd_id == "param.reset":
            default = copy.deepcopy(DEFAULT_PATCH)
            dmap = patch_node_map(default)
            if info["node"] in dmap and info["param"] in dmap[info["node"]].get("params", {}):
                _set_param(st.patch, rid, dmap[info["node"]]["params"][info["param"]])
                st.dirty = True
                return "%s reset" % PARAM_ROWS[st.param_sel][1]
            return "no factory default"
        if cmd_id == "param.max":
            _set_param(st.patch, rid, info["hi"])
        elif cmd_id == "param.min":
            _set_param(st.patch, rid, info["lo"])
        else:
            step = info["step"] * (1 if cmd_id == "param.inc" else -1)
            _set_param(st.patch, rid, cur + step)
        st.dirty = True
        return "%s = %s" % (PARAM_ROWS[st.param_sel][1], _get_param(st.patch, rid))
    if cmd_id == "patch.new":
        st.patch = copy.deepcopy(DEFAULT_PATCH)
        st.patch_path = None
        st.dirty = True
        return "init patch (unsaved)"
    if cmd_id == "patch.open":
        entries = _browser_entries(st)
        if entries:
            kind, name, path = entries[clamp(st.browser_sel, 0, len(entries) - 1)]
            if kind == "patch":
                return run_command(st, "patch.open-path", path or "built-in")
            st.overlay = "theme"
            return "theme list focused"
        return "nothing to open"
    if cmd_id == "patch.open-path":
        if arg in (None, "built-in"):
            st.patch = copy.deepcopy(DEFAULT_PATCH)
            st.patch_path = None
        else:
            loaded, errs = load_patch_file(arg)
            if loaded is None:
                return "open failed: %s" % "; ".join(errs[:2])
            if errs:
                return "patch invalid: %s" % "; ".join(errs[:2])
            st.patch = loaded
            st.patch_path = arg
        st.dirty = False
        st.fingerprint = st._fingerprint()
        return "opened %s" % st.patch.get("id", "?")
    if cmd_id == "patch.save":
        if not st.patch_path:
            st.overlay = "input"
            st.input_title = "Save as (patches/)"
            st.input_text = "%s.json" % st.patch.get("id", "patch")
            st.input_accept = "patch.save-as-confirm"
            return "name a file"
        errs = validate_patch(st.patch)
        if errs:
            return "cannot save: %s" % errs[0]
        atomic_write_text(st.patch_path, json.dumps(st.patch, indent=1))
        st.dirty = False
        return "saved %s" % os.path.basename(st.patch_path)
    if cmd_id == "patch.save-as":
        st.overlay = "input"
        st.input_title = "Save as (patches/)"
        st.input_text = "%s.json" % st.patch.get("id", "patch")
        st.input_accept = "patch.save-as-confirm"
        return "name a file"
    if cmd_id == "patch.save-as-confirm":
        name = (arg or "").strip() or ("%s.json" % st.patch.get("id", "patch"))
        if not name.endswith(".json"):
            name += ".json"
        dest = name if os.path.isabs(name) else os.path.join(st.patch_dir, os.path.basename(name))
        if os.path.isfile(dest):
            return "refusing to overwrite %s" % os.path.basename(dest)
        errs = validate_patch(st.patch)
        if errs:
            return "cannot save: %s" % errs[0]
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        atomic_write_text(dest, json.dumps(st.patch, indent=1))
        st.patch_path = dest
        st.dirty = False
        return "saved %s" % os.path.basename(dest)
    if cmd_id == "patch.revert":
        if st.patch_path and os.path.isfile(st.patch_path):
            return run_command(st, "patch.open-path", st.patch_path)
        st.patch = copy.deepcopy(DEFAULT_PATCH)
        st.dirty = True
        return "reverted to built-in"
    if cmd_id == "render.wav":
        st.overlay = "input"
        st.input_title = "Render to WAV"
        st.input_text = "render-%s.wav" % st.patch.get("id", "patch")
        st.input_accept = "render.wav-confirm"
        return "name a file"
    if cmd_id == "render.wav-confirm":
        name = (arg or "").strip() or ("render-%s.wav" % st.patch.get("id", "patch"))
        dest = name if os.path.isabs(name) else os.path.join(os.getcwd(), name)
        try:
            stereo = render_patch(st.patch, make_chord(AUDITION_CHORD, 4.0, st.vel), 4.0, st.sr, st.seed)
            g = st.cfg["audio"]["master_gain"]
            stereo = ([clamp(v * g, -1.0, 1.0) for v in stereo[0]],
                      [clamp(v * g, -1.0, 1.0) for v in stereo[1]])
            write_wav(dest, stereo, st.sr)
        except Exception as exc:
            return "render failed: %s" % exc
        return "rendered %s (peak %.2f)" % (os.path.basename(dest), buffer_peak(stereo))
    if cmd_id in ("tile.focus-1", "tile.focus-2", "tile.focus-3", "tile.focus-4",
                    "tile.focus-5"):
        want = {"tile.focus-1": "browser", "tile.focus-2": "pads",
                "tile.focus-3": "voice", "tile.focus-4": "mod",
                "tile.focus-5": "piano"}[cmd_id]
        if want in st.hidden:
            st.hidden.discard(want)
        st.focus_tile = want
        return "focus %s" % want
    if cmd_id in ("tile.next", "tile.prev"):
        order = ["browser", "pads", "voice", "mod", "piano"]
        vis = [t for t in order if t not in st.hidden] or order
        i = vis.index(st.focus_tile) if st.focus_tile in vis else 0
        st.focus_tile = vis[(i + (1 if cmd_id == "tile.next" else -1)) % len(vis)]
        return "focus %s" % st.focus_tile
    if cmd_id.startswith("tile.toggle-"):
        tile = cmd_id.rsplit("-", 1)[1]
        if tile in st.hidden:
            st.hidden.discard(tile)
            st.focus_tile = tile
            return "show %s" % tile
        if len(st.hidden) >= 4:
            return "at least one tile must stay visible"
        st.hidden.add(tile)
        if st.focus_tile == tile:
            st.focus_tile = next(t for t in ("browser", "pads", "voice", "mod", "piano")
                                 if t not in st.hidden)
        return "hide %s" % tile
    if cmd_id == "layout.restore":
        st.hidden = set()
        st.ratios = {"left": 0.24, "center": 0.40, "voice": 0.55}
        st.focus_tile = "pads"
        return "tiles restored"
    if cmd_id == "divider.left.inc":
        st.ratios["left"] = clamp(st.ratios["left"] + 0.02, 0.1, 0.8)
        return "browser %d%%" % int(st.ratios["left"] * 100)
    if cmd_id == "divider.left.dec":
        st.ratios["left"] = clamp(st.ratios["left"] - 0.02, 0.1, 0.8)
        return "browser %d%%" % int(st.ratios["left"] * 100)
    if cmd_id == "divider.center.inc":
        st.ratios["center"] = clamp(st.ratios["center"] + 0.02, 0.1, 0.8)
        return "pads %d%%" % int(st.ratios["center"] * 100)
    if cmd_id == "divider.center.dec":
        st.ratios["center"] = clamp(st.ratios["center"] - 0.02, 0.1, 0.8)
        return "pads %d%%" % int(st.ratios["center"] * 100)
    if cmd_id == "theme.choose":
        st.theme_backup = st.theme
        st.overlay = "theme"
        return "theme chooser: arrows preview, ENTER commits, ESC restores"
    if cmd_id in ("theme.next", "theme.prev"):
        ids = ["minimal"] + sorted(st.catalog)
        if st.theme_id not in ids:
            ids.append(st.theme_id)
        i = ids.index(st.theme_id)
        nxt = ids[(i + (1 if cmd_id == "theme.next" else -1)) % len(ids)]
        return _apply_theme_by_id(st, nxt, commit=True)
    if cmd_id == "motion.cycle":
        order = ["off", "reduced", "normal", "high"]
        cur = st.cfg["appearance"]["motion"]
        st.cfg["appearance"]["motion"] = order[(order.index(cur) + 1) % 4]
        return "motion %s" % st.cfg["appearance"]["motion"]
    if cmd_id == "immersive.toggle":
        st.cfg["appearance"]["immersive"] = not st.cfg["appearance"]["immersive"]
        return "immersive %s" % ("on" if st.cfg["appearance"]["immersive"] else "off")
    if cmd_id in ("palette.open", "ribbon.focus", "help.show", "diagnostics.show", "menu.open"):
        st.overlay = {"palette.open": "palette", "ribbon.focus": "ribbon",
                      "help.show": "help", "diagnostics.show": "diag",
                      "menu.open": "menu"}[cmd_id]
        st.palette_filter = ""
        st.palette_sel = 0
        return st.overlay
    if cmd_id == "overlay.dismiss":
        if st.overlay == "theme" and st.theme_backup is not None:
            st.theme = st.theme_backup
            st.theme_id = st.theme.get("id", st.theme_id)
            st.theme_backup = None
        st.overlay = None
        return "dismissed"
    if cmd_id in ("browser.scroll-up", "browser.scroll-down"):
        d = -1 if cmd_id == "browser.scroll-up" else 1
        st.browser_sel = max(0, st.browser_sel + d * 4)
        return "browser row %d" % (st.browser_sel + 1)
    if cmd_id == "quit.request":
        if st.dirty:
            st.overlay = "confirm"
            return "unsaved changes"
        return "__quit__"
    if cmd_id not in cmds:
        return "unknown command %r" % cmd_id
    return cmds and ""


def _apply_theme_by_id(state, tid, commit=False):
    if tid == "minimal":
        state.theme = dict(MINIMAL_THEME)
        state.theme_id = "minimal"
    else:
        path = state.catalog.get(tid)
        if path is None:
            return "unknown theme %r" % tid
        loaded, errs, _warns = load_theme_file(path, state.catalog)
        if loaded is None:
            return "theme %r rejected (%s); kept %s" % (tid, errs[0] if errs else "?", state.theme_id)
        state.theme = loaded
        state.theme_id = tid
    if commit:
        try:
            save_session(state.cfg, {"theme": state.theme_id, "ratios": state.ratios,
                                     "octave": state.octave, "piano_base": state.piano_base})
        except OSError:
            pass
        return "theme %s" % tid
    return "preview %s (ENTER commits)" % tid


HELP_TEXT = """PADSYNTH 0.1.0 // PADS STRINGS AIR AMBIENCE
MOUSE IS FIRST CLASS. KEYS DO EVERYTHING THE MOUSE CAN.
  click pad          trigger (x position = velocity) .... keys 1-9 A-G / arrows+SPACE
  click button row   AUDITION STOP DRONE OCT VEL ........ SPACE SH+D + - [ ]
  piano click        play note (lower = louder) ......... ZSXDCVGBHNJM row
  piano bottom rows  full-velocity safe zone ........... click anywhere low
  piano octave       shift keyboard/map range .......... , .
  click slider       set parameter ..................... LEFT/RIGHT/HOME/END
  right-click slider reset to factory ................. key 0
  click tile         focus + act ....................... TAB / ESC 1..4
  click row          select; click again opens ......... arrows + ENTER
  right-click tile   open menu ......................... ESC m
  click divider      step by half ...................... < > { }
  wheel              scroll tile / octave / params ..... PGUP/PGDN
  outside click      dismiss overlay (consumed) ........ ESC (closes exactly one)
  ribbon buttons     open menu ......................... F10 then arrows+ENTER
EMERGENCY ROUTES (cannot be rebound): CTRL+P palette, CTRL+T restore tiles,
F10 ribbon, F1 help, CTRL+Q quit with dirty guard.
KEYS: SH+D drone · O motion · I immersive · M theme back · F8 theme next.
DEMO: `python padsynth.py --demo` prints the tour and renders demo-medley.wav;
`--demo-play` also plays it. In the TUI, palette command demo.medley plays it.
SESSION lives in .padsynth/ as local plaintext (not encrypted); recovery never
silently overwrites a patch. Config padsynth.conf is never rewritten by the app.
THEMES are md-editor-theme/1.1 data; unknown fields fail; a rejected candidate
never partially updates the live skin. Motion off/reduced/normal/high; the host
cap wins; style/palette tracks capped at 2 Hz; spatial tracks at theme cadence.
GAPS IN 0.1.0 (honest): no timer-driven ambient animation (event repaints only),
no submenus (palette covers depth), no fullscreen single-tile zoom beyond hiding
other tiles, winsound loop holds state instead of looping audio.
"""


def run_tui(cfg, cfg_diags, patch, patch_arg, theme, theme_id, catalog, patch_dir,
            seed, sr, backend, lock_warn, sess, args, app_input=None, app_output=None):
    try:
        from prompt_toolkit import Application
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.keys import Keys
        from prompt_toolkit.layout import (ConditionalContainer, DynamicContainer,
                                           Float, FloatContainer, HSplit, Layout,
                                           VSplit, Window)
        from prompt_toolkit.layout.controls import FormattedTextControl
        from prompt_toolkit.mouse_events import MouseEventType
        from prompt_toolkit.styles import Style
        from prompt_toolkit.filters import Condition
        from prompt_toolkit.widgets import Frame
    except ImportError:
        print("interactive TUI needs prompt_toolkit>=3.0.53: pip install -r requirements.txt")
        print("non-interactive paths work: --diagnostics --snapshot 100x28 --render out.wav")
        return 2

    class _ClickableText(FormattedTextControl):
        """FormattedTextControl with a per-instance mouse handler.

        prompt_toolkit routes Window mouse events to
        control.mouse_handler(); the base control class carries no
        constructor hook, so this subclass holds the handler.
        """

        def __init__(self, text, handler=None, **kw):
            super().__init__(text, **kw)
            self._click_handler = handler

        def mouse_handler(self, mouse_event):
            if self._click_handler is None:
                return NotImplemented
            return self._click_handler(mouse_event)

    state = TuiState(cfg, patch, patch_arg if patch_arg and os.path.isfile(patch_arg) else None,
                     theme, theme_id, catalog, patch_dir, seed, sr, backend, sess or {})
    if lock_warn:
        state.lock_warn = lock_warn
        state.message = lock_warn
    if cfg_diags:
        state.message = "config: %s" % cfg_diags[0][:60]

    smap = theme_style_map(state.theme)
    ascii_only = cfg["accessibility"]["ascii_only"] or not cfg["capabilities"]["unicode"]
    div_char = "|" if ascii_only else "│"

    def sty(name, fallback_fg="#d8e9f2", fallback_bg="#05070b"):
        s = smap.get(name, {})
        fg = s.get("fg", fallback_fg)
        bg = s.get("bg", fallback_bg)
        depth = cfg["capabilities"]["colour_depth"]
        if depth not in ("auto", "truecolour"):
            fg = quantize_hex(fg, depth)
            bg = quantize_hex(bg, depth)
        extra = "".join(" " + k for k in ("bold", "italic", "underline", "dim", "strike")
                        if s.get(k))
        return ("%s bg:%s%s" % (fg, bg, extra)).strip()

    _paper_bg = smap.get("base", {}).get("bg", "#000000")
    _frame_fg = smap.get("frame", {}).get("fg", "#444444")
    _depth = cfg["capabilities"]["colour_depth"]
    if _depth not in ("auto", "truecolour"):
        _paper_bg = quantize_hex(_paper_bg, _depth)
        _frame_fg = quantize_hex(_frame_fg, _depth)
    _piano_black = "%s bg:%s" % (_paper_bg, _frame_fg)

    style = Style.from_dict({
        "topbar": sty("accent"), "ribbon": sty("frame"), "status": sty("muted"),
        "tiletitle": sty("accent"), "tilefoot": sty("muted"), "slider": sty("base"),
        "pad": sty("base"), "padhot": sty("accent"), "dialog": sty("base"),
        "error": "ansired bold", "ok": "ansigreen",
        "button": sty("frame"), "button.focused": sty("accent"),
        "piano.white": sty("base"), "piano.black": _piano_black, "piano.hot": sty("accent"),
    })

    kb = KeyBindings()
    app_ref = {}

    def refresh():
        app = app_ref.get("app")
        if app is not None:
            app.invalidate()

    def audio_notify():
        err = _audio_state.pop("error", None)
        if err:
            state.message = "audio: %s" % err[:70]
        elif not _audio_state["playing"]:
            state.message = "played via %s" % state.backend[0]
        app = app_ref.get("app")
        if app is not None:
            try:
                app.call_from_executor(refresh)
            except Exception:
                try:
                    app.invalidate()
                except Exception:
                    pass

    state.audio_notify = audio_notify

    def do(cmd, arg=None):
        msg = run_command(state, cmd, arg)
        if msg == "__quit__":
            stop_playback()
            try:
                save_session(cfg, {"theme": state.theme_id, "ratios": state.ratios,
                                   "octave": state.octave, "piano_base": state.piano_base})
            except OSError:
                pass
            app_ref["app"].exit()
            return
        if msg:
            state.message = msg
        refresh()

    # -- text painters ------------------------------------------------------
    def top_frags():
        dirty = " ●" if state.dirty else ""
        name = str(state.patch.get("name", state.patch.get("id", "?")))
        return [("class:topbar",
                 ("PADSYNTH /// %s%s /// %s /// %s" % (
                     name.upper(), dirty, state.theme_id,
                      state.backend[0])).ljust(78))]

    def ribbon_frags():
        parts = []
        for i, (head, _items) in enumerate(RIBBON_MENUS):
            hot = state.overlay in ("ribbon", "menu") and state.menu_for == head
            parts.append(("class:button.focused" if hot else "class:button",
                          " %s " % head if i else "[%s] " % head))
        parts.append(("class:status", "  F10 menus · CTRL+P palette · F1 help"))
        return parts

    def status_frags():
        err = _audio_state.pop("error", None)
        if err:
            state.message = "audio: %s" % err[:60]
        motion = cfg["appearance"]["motion"]
        play = "▶ " if _audio_state["playing"] else ""
        return [("class:status",
                 ("%s[%s] voices %d · %s · motion %s · oct %+d vel %.2f · %s" % (
                     play, state.focus_tile.upper(), cfg["audio"]["polyphony"],
                     state.backend[0], motion, state.octave, state.vel,
                     state.message)).ljust(78))]

    def pads_frags():
        out = []
        for r in range(4):
            for c in range(4):
                idx = r * 4 + c
                hot = idx == state.pad_cursor
                label = "%02d" % (idx + 1)
                cell = "[%s%s]" % (label, "*" if hot and state.focus_tile == "pads" else " ")
                out.append(("class:padhot" if hot else "class:pad", cell + " "))
            out.append(("", "\n"))
        out.append(("class:button", "[AUDITION] [STOP] [DRONE]  [OCT-][OCT+][VEL-][VEL+]"))
        out.append(("", "\n"))
        out.append(("class:tilefoot", "click pad = trigger · x = velocity · SPACE audition · D drone"))
        return out

    # fixed button-row spans inside the pads tile (see pads_frags above)
    PAD_BUTTONS = [
        (0, 11, "audition.start"), (11, 18, "audition.stop"), (18, 27, "drone.toggle"),
        (27, 33, "octave.down"), (33, 39, "octave.up"),
        (40, 46, "velocity.down"), (47, 53, "velocity.up"),
    ]

    def slider_line(rid, label, selected):
        val = _get_param(state.patch, rid)
        info = _row_info(state.patch, rid)
        if info is None or val is None:
            return [("class:tilefoot", "%-12s n/a in this patch\n" % label)]
        frac = _value_to_frac(info, val)
        fill = int(frac * BAR_W)
        bar = "#" * fill + "-" * (BAR_W - fill)
        if isinstance(val, float):
            vtxt = ("%.2f" % val) if abs(val) < 100 else ("%d" % int(val))
        else:
            vtxt = str(val)
        mark = ">" if selected else " "
        return [("class:slider", "%s%-12s [%s] %s\n" % (mark, label, bar, vtxt))]

    def voice_frags():
        rows = [r for r in PARAM_ROWS if r[0].split(".")[0] in ("osc", "ens", "air", "flt", "env")]
        out = []
        for i, (rid, label, _n, _p, _s) in enumerate(rows):
            out += slider_line(rid, label, state.focus_tile == "voice" and i == state.param_sel % len(rows))
        return out

    def mod_frags():
        rows = [r for r in PARAM_ROWS if r[0].split(".")[0] in ("lfo", "mod", "fx", "out")]
        out = []
        for i, (rid, label, _n, _p, _s) in enumerate(rows):
            out += slider_line(rid, label, state.focus_tile == "mod" and i == state.param_sel % len(rows))
        return out

    def browser_frags():
        entries = _browser_entries(state)
        out = []
        for i, (kind, name, _p) in enumerate(entries[:24]):
            mark = ">" if i == state.browser_sel else " "
            cur = ""
            if kind == "theme" and name == state.theme_id:
                cur = " *"
            out.append(("class:slider" if kind == "patch" else "class:pad",
                        "%s[%s] %s%s\n" % (mark, kind[0].upper(), name[:34], cur)))
        return out

    def piano_frags():
        now = time.time()
        base = state.piano_base
        mono = cfg["capabilities"]["colour_depth"] == "mono"
        width = PIANO_WHITE_N * PIANO_WHITE_W
        out = []
        for y in range(PIANO_ROWS):
            for x in range(width):
                midi, black = piano_key_at(base, x, y)
                ch = " "
                if black:
                    ch = "#" if mono else " "
                elif y == PIANO_ROWS - 1:
                    wi = x // PIANO_WHITE_W
                    bx = x - wi * PIANO_WHITE_W
                    if bx == 2:
                        ch = PIANO_LETTERS[wi % 7]
                    elif bx == 3 and wi % 7 == 0:
                        ch = str((piano_white_midi(base, wi) // 12) - 1)
                hot = midi in state.piano_hot and now - state.piano_hot[midi] < 0.5
                if hot:
                    cls = "piano.hot"
                    ch = "*" if mono else ch
                elif black:
                    cls = "piano.black"
                else:
                    cls = "piano.white"
                out.append((("class:" + cls), ch))
            out.append(("", "\n"))
        return out

    # -- mouse handlers -------------------------------------------------------
    def pads_mouse(ev):
        if ev.event_type == MouseEventType.SCROLL_UP:
            do("octave.up")
            return None
        if ev.event_type == MouseEventType.SCROLL_DOWN:
            do("octave.down")
            return None
        if ev.button == "RIGHT":
            if ev.event_type == MouseEventType.MOUSE_DOWN:
                state.focus_tile = "pads"
                state.message = "pads focused (right-click never triggers)"
                refresh()
            return None
        if ev.event_type != MouseEventType.MOUSE_UP:
            return None
        state.focus_tile = "pads"
        if ev.position.y == 4:
            for x0, x1, cmd in PAD_BUTTONS:
                if x0 <= ev.position.x < x1:
                    do(cmd)
                    return None
            return None
        col = clamp(ev.position.x // 6, 0, 3)
        row = clamp(ev.position.y, 0, 3)
        idx = row * 4 + col
        vel = clamp(0.35 + 0.65 * ((ev.position.x % 6) / 6.0), 0.1, 1.0)
        do("pad.trigger-%02d" % (idx + 1), vel)
        return None

    def make_slider_mouse(tile, row_ids):
        def handler(ev):
            if ev.event_type in (MouseEventType.SCROLL_UP, MouseEventType.SCROLL_DOWN):
                state.focus_tile = tile
                d = 1 if ev.event_type == MouseEventType.SCROLL_UP else -1
                state.param_sel = (state.param_sel + d) % len(PARAM_ROWS)
                refresh()
                return None
            if ev.button == "RIGHT":
                if ev.event_type == MouseEventType.MOUSE_DOWN:
                    state.focus_tile = tile
                    y = clamp(ev.position.y, 0, len(row_ids) - 1)
                    rid = row_ids[y]
                    state.param_sel = next(i for i, r in enumerate(PARAM_ROWS) if r[0] == rid)
                    do("param.reset")
                return None
            if ev.event_type != MouseEventType.MOUSE_UP:
                return None
            state.focus_tile = tile
            y = clamp(ev.position.y, 0, len(row_ids) - 1)
            # map visible row -> global PARAM_ROWS index
            rid = row_ids[y]
            state.param_sel = next(i for i, r in enumerate(PARAM_ROWS) if r[0] == rid)
            if ev.button == "RIGHT":
                do("param.reset")
                return None
            info = _row_info(state.patch, rid)
            if info is None:
                return None
            frac = clamp((ev.position.x - BAR_COL) / float(BAR_W), 0.0, 1.0)
            err = _set_param(state.patch, rid, _frac_to_value(info, frac))
            if err:
                state.message = err
            else:
                state.dirty = True
                state.message = "%s = %s" % (rid, _get_param(state.patch, rid))
            refresh()
            return None
        return handler

    def browser_mouse(ev):
        if ev.event_type in (MouseEventType.SCROLL_UP, MouseEventType.SCROLL_DOWN):
            do("browser.scroll-up" if ev.event_type == MouseEventType.SCROLL_UP
               else "browser.scroll-down")
            return None
        if ev.button == "RIGHT":
            if ev.event_type == MouseEventType.MOUSE_DOWN:
                state.focus_tile = "browser"
                state.overlay = "menu"
                state.menu_for = "PATCH"
                refresh()
            return None
        if ev.event_type != MouseEventType.MOUSE_UP:
            return None
        # click selects; clicking the already-selected row activates it
        state.focus_tile = "browser"
        entries = _browser_entries(state)
        idx = clamp(ev.position.y, 0, len(entries) - 1)
        if idx == state.browser_sel:
            do("patch.open")
        else:
            state.browser_sel = idx
            refresh()
        return None

    def divider_mouse(which):
        def handler(ev):
            if ev.button == "RIGHT" or ev.event_type != MouseEventType.MOUSE_UP:
                return None
            if ev.position.x <= 0:
                do("divider.%s.dec" % which)
            else:
                do("divider.%s.inc" % which)
            return None
        return handler

    def ribbon_mouse(ev):
        if ev.button == "RIGHT" or ev.event_type != MouseEventType.MOUSE_UP:
            return None
        idx = clamp(ev.position.x // 10, 0, len(RIBBON_MENUS) - 1)
        state.menu_for = RIBBON_MENUS[idx][0]
        state.overlay = "menu"
        refresh()
        return None

    def piano_mouse(ev):
        if ev.event_type in (MouseEventType.SCROLL_UP, MouseEventType.SCROLL_DOWN):
            do("piano.octave.up" if ev.event_type == MouseEventType.SCROLL_UP
               else "piano.octave.down")
            return None
        if ev.button == "RIGHT":
            if ev.event_type == MouseEventType.MOUSE_DOWN:
                state.focus_tile = "piano"
                state.message = "piano focused (right-click never plays)"
                refresh()
            return None
        if ev.event_type != MouseEventType.MOUSE_UP:
            return None
        state.focus_tile = "piano"
        x = clamp(ev.position.x, 0, PIANO_WHITE_N * PIANO_WHITE_W - 1)
        y = clamp(ev.position.y, 0, PIANO_ROWS - 1)
        midi, _black = piano_key_at(state.piano_base, x, y)
        do("piano.key", (midi - state.piano_base, piano_velocity(y)))
        return None

    def backdrop_mouse(ev):
        # outside-click dismisses exactly one overlay and consumes the click
        if ev.event_type != MouseEventType.MOUSE_UP:
            return None
        if state.overlay:
            do("overlay.dismiss")
        return None

    # -- overlays ---------------------------------------------------------------
    def palette_items():
        items = _filtered_commands(state)
        return items[:14]

    def overlay_frags():
        if state.overlay == "help":
            return [("", HELP_TEXT)]
        if state.overlay == "diag":
            d = build_diagnostics(cfg, cfg_diags, state.theme, [], state.patch,
                                  validate_patch(state.patch), state.backend, state.lock_warn)
            return [("", d)]
        if state.overlay in ("palette", "ribbon", "menu"):
            if state.overlay == "palette":
                items = palette_items()
                lines = [("class:tiletitle", "PALETTE  filter: %s_\n" % state.palette_filter)]
                for i, c in enumerate(items):
                    mark = ">" if i == state.palette_sel else " "
                    keys = ",".join(c["keys"]) if c["keys"] else "--"
                    lines.append(("class:slider", "%s %-22s [%s]\n" % (mark, c["id"], keys)))
                lines.append(("class:tilefoot", "type to filter · UP/DN select · ENTER run · ESC dismiss"))
                return lines
            heads = RIBBON_MENUS if state.overlay == "ribbon" else [
                (state.menu_for, dict(RIBBON_MENUS)[state.menu_for])]
            lines = [("class:tiletitle", "MENUS (single level; palette covers depth)\n")]
            n = 0
            for head, ids in heads:
                for cid in ids:
                    title = next((c["title"] for c in COMMANDS if c["id"] == cid), cid)
                    mark = ">" if n == state.palette_sel else " "
                    lines.append(("class:slider", "%s %s > %s\n" % (mark, head, title)))
                    n += 1
            lines.append(("class:tilefoot", "UP/DN select · ENTER run · ESC dismiss"))
            return lines
        if state.overlay == "theme":
            ids = ["minimal"] + sorted(catalog)
            lines = [("class:tiletitle", "THEME (arrows preview · ENTER commits · ESC restores)\n")]
            for i, tid in enumerate(ids[:16]):
                mark = ">" if tid == state.theme_id else " "
                lines.append(("class:slider", "%s %s\n" % (mark, tid)))
            return lines
        if state.overlay == "confirm":
            return [("class:error", "UNSAVED CHANGES\n"),
                    ("", "ENTER=save+quit  D=discard+quit  ESC=stay\n")]
        if state.overlay == "input":
            return [("class:tiletitle", "%s\n" % state.input_title),
                    ("class:slider", "%s_\n" % state.input_text),
                    ("class:tilefoot", "type · ENTER accept · ESC cancel")]
        return [("", "")]

    # -- layout ------------------------------------------------------------------
    pads_win = Window(content=_ClickableText(pads_frags, handler=pads_mouse,
                                             focusable=True))
    voice_ids = [r[0] for r in PARAM_ROWS if r[0].split(".")[0] in ("osc", "ens", "air", "flt", "env")]
    mod_ids = [r[0] for r in PARAM_ROWS if r[0].split(".")[0] in ("lfo", "mod", "fx", "out")]
    voice_win = Window(content=_ClickableText(
        voice_frags, handler=make_slider_mouse("voice", voice_ids), focusable=True))
    mod_win = Window(content=_ClickableText(
        mod_frags, handler=make_slider_mouse("mod", mod_ids), focusable=True))
    browser_win = Window(content=_ClickableText(
        browser_frags, handler=browser_mouse, focusable=True))
    piano_win = Window(content=_ClickableText(
        piano_frags, handler=piano_mouse, focusable=True))

    def term_cols():
        try:
            return int(app_ref["app"].output.get_size().columns)
        except Exception:
            return 80

    def piano_title():
        lo = midi_to_name(state.piano_base)
        hi = midi_to_name(clamp(state.piano_base + 23, 0, 127))
        return "PIANO %s-%s · lower click = louder · bottom %d rows = FULL" % (
            lo, hi, PIANO_SAFE_ROWS)

    def main_container():
        cols = []
        if "browser" not in state.hidden:
            cols.append(Frame(body=browser_win, title="BROWSER patches/themes"))
        if "browser" not in state.hidden and any(t not in state.hidden for t in ("pads", "voice", "mod")):
            cols.append(Window(width=1, content=_ClickableText(
                lambda: [("class:ribbon", div_char)], handler=divider_mouse("left"))))
        if "pads" not in state.hidden:
            cols.append(Frame(body=pads_win, title="PADS trigger"))
        right = []
        if "voice" not in state.hidden:
            right.append(Frame(body=voice_win, title="VOICE osc/filter/env"))
        if "mod" not in state.hidden:
            right.append(Frame(body=mod_win, title="MOD fx/master"))
        if right and "pads" not in state.hidden:
            cols.append(Window(width=1, content=_ClickableText(
                lambda: [("class:ribbon", div_char)], handler=divider_mouse("center"))))
        if right:
            cols.append(HSplit(right))
        if not cols:
            cols.append(Window(content=FormattedTextControl(lambda: [("", "all tiles hidden")])))
        lower = [VSplit(cols, padding=1)]
        if ("piano" not in state.hidden and cfg["layout"].get("piano_visible", True)
                and term_cols() >= PIANO_WHITE_N * PIANO_WHITE_W + 2):
            lower.append(Frame(body=piano_win, title=piano_title()))
        lower.append(
            Window(content=_ClickableText(
                status_frags,
                handler=lambda ev: do("help.show")
                if ev.button != "RIGHT" and ev.event_type == MouseEventType.MOUSE_UP
                else None), height=1))
        return HSplit([
            Window(content=FormattedTextControl(top_frags), height=1),
            Window(content=_ClickableText(ribbon_frags, handler=ribbon_mouse), height=1),
        ] + lower)

    overlay_win = Window(content=FormattedTextControl(overlay_frags, focusable=True))
    backdrop = Window(content=_ClickableText(lambda: [("", "")],
                                             handler=backdrop_mouse))
    def overlay_visible():
        return state.overlay is not None

    # -- keys ----------------------------------------------------------------------
    # NOTE: the processor calls exactly ONE handler per key (exact bindings
    # shadow Keys.Any), so every single-character binding below first offers
    # the key to overlay text entry / confirm before acting.
    def offer_to_overlay(data):
        if not isinstance(data, str) or len(data) != 1 or not data.isprintable():
            return False
        if state.overlay == "input":
            state.input_text += data
            refresh()
            return True
        if state.overlay == "palette":
            state.palette_filter += data
            state.palette_sel = 0
            refresh()
            return True
        if state.overlay == "confirm" and data.lower() == "d":
            state.overlay = None
            stop_playback()
            app_ref["app"].exit()
            return True
        return False
    @kb.add("c-p")
    def _(ev):
        do("palette.open")

    @kb.add("c-t")
    def _(ev):
        do("layout.restore")

    @kb.add("c-q")
    def _(ev):
        do("quit.request")

    @kb.add("f10")
    def _(ev):
        do("ribbon.focus")

    @kb.add("f1")
    def _(ev):
        do("help.show")

    @kb.add("f8")
    def _(ev):
        if not state.overlay:
            do("theme.next")

    @kb.add("M")
    def _(ev):
        if not state.overlay:
            do("theme.prev")

    @kb.add("f9")
    def _(ev):
        do("diagnostics.show")

    @kb.add("tab")
    def _(ev):
        do("tile.next")

    @kb.add("s-tab")
    def _(ev):
        do("tile.prev")

    for _n, _t in (("1", "tile.focus-1"), ("2", "tile.focus-2"),
                   ("3", "tile.focus-3"), ("4", "tile.focus-4"),
                   ("5", "tile.focus-5")):
        @kb.add("escape", _n)
        def _(ev, _t=_t):
            if not state.overlay:
                do(_t)

    @kb.add("escape", "m")
    def _(ev):
        if not state.overlay:
            do("menu.open")

    @kb.add("escape")
    def _(ev):
        if state.overlay:
            do("overlay.dismiss")
        else:
            do("audition.stop")

    @kb.add("enter")
    def _(ev):
        if state.overlay == "palette":
            items = palette_items()
            if items:
                cmd = items[clamp(state.palette_sel, 0, len(items) - 1)]["id"]
                state.overlay = None
                do(cmd)
        elif state.overlay in ("ribbon", "menu"):
            # activate highlighted menu row
            heads = RIBBON_MENUS if state.overlay == "ribbon" else [
                (state.menu_for, dict(RIBBON_MENUS)[state.menu_for])]
            flat = [cid for _h, ids in heads for cid in ids]
            if flat:
                cmd = flat[clamp(state.palette_sel, 0, len(flat) - 1)]
                state.overlay = None
                do(cmd)
        elif state.overlay == "theme":
            state.theme_backup = None
            _apply_theme_by_id(state, state.theme_id, commit=True)
            state.overlay = None
            refresh()
        elif state.overlay == "confirm":
            state.overlay = None
            if state.patch_path or True:
                msg = run_command(state, "patch.save") if state.patch_path else None
                if msg and msg.startswith("name a file"):
                    state.overlay = "input"
                    state.input_title = "Save before quit"
                    state.input_text = "%s.json" % state.patch.get("id", "patch")
                    state.input_accept = "patch.save-as-confirm-quit"
                    refresh()
                    return
            stop_playback()
            app_ref["app"].exit()
        elif state.overlay == "input" and state.input_accept:
            accept = state.input_accept
            given = state.input_text
            if accept == "patch.save-as-confirm-quit":
                msg = run_command(state, "patch.save-as-confirm", given)
                state.overlay = None
                if msg.startswith("saved"):
                    stop_playback()
                    app_ref["app"].exit()
                else:
                    state.message = msg
                refresh()
                return
            state.overlay = None
            do(accept, given)
        elif state.focus_tile == "pads":
            do("pad.trigger-%02d" % (state.pad_cursor + 1))
        elif state.focus_tile == "browser":
            do("patch.open")

    @kb.add("up")
    def _(ev):
        if state.overlay in ("palette", "ribbon", "menu"):
            state.palette_sel = max(0, state.palette_sel - 1)
        elif state.overlay == "theme":
            ids = ["minimal"] + sorted(catalog)
            i = ids.index(state.theme_id) if state.theme_id in ids else 0
            _apply_theme_by_id(state, ids[(i - 1) % len(ids)])
        elif state.overlay == "help":
            state.help_scroll = max(0, state.help_scroll - 1)
        elif state.focus_tile == "browser":
            state.browser_sel = max(0, state.browser_sel - 1)
        elif state.focus_tile == "pads":
            state.pad_cursor = (state.pad_cursor - 4) % 16
        else:
            do("param.prev")
            return
        refresh()

    @kb.add("down")
    def _(ev):
        if state.overlay in ("palette", "ribbon", "menu"):
            state.palette_sel += 1
        elif state.overlay == "theme":
            ids = ["minimal"] + sorted(catalog)
            i = ids.index(state.theme_id) if state.theme_id in ids else 0
            _apply_theme_by_id(state, ids[(i + 1) % len(ids)])
        elif state.overlay == "help":
            state.help_scroll += 1
        elif state.focus_tile == "browser":
            state.browser_sel += 1
        elif state.focus_tile == "pads":
            state.pad_cursor = (state.pad_cursor + 4) % 16
        else:
            do("param.next")
            return
        refresh()

    @kb.add("left")
    def _(ev):
        if state.overlay:
            return
        if state.focus_tile == "pads":
            state.pad_cursor = (state.pad_cursor - 1) % 16
            refresh()
        elif state.focus_tile in ("voice", "mod") and not state.overlay:
            do("param.dec")
        elif state.focus_tile == "browser":
            state.browser_sel = max(0, state.browser_sel - 1)
            refresh()

    @kb.add("right")
    def _(ev):
        if state.overlay:
            return
        if state.focus_tile == "pads":
            state.pad_cursor = (state.pad_cursor + 1) % 16
            refresh()
        elif state.focus_tile in ("voice", "mod") and not state.overlay:
            do("param.inc")

    @kb.add("home")
    def _(ev):
        if state.focus_tile in ("voice", "mod") and not state.overlay:
            do("param.min")

    @kb.add("end")
    def _(ev):
        if state.focus_tile in ("voice", "mod") and not state.overlay:
            do("param.max")

    @kb.add("pageup")
    def _(ev):
        do("browser.scroll-up")

    @kb.add("pagedown")
    def _(ev):
        do("browser.scroll-down")

    @kb.add(" ")
    def _(ev):
        if offer_to_overlay(" "):
            return
        if not state.overlay:
            do("audition.start")

    for _ch, _cmd in [("D", "drone.toggle"), ("o", "motion.cycle"), ("i", "immersive.toggle"),
                      ("+", "octave.up"), ("-", "octave.down"), ("]", "velocity.up"),
                      ("[", "velocity.down"), ("0", "param.reset"),
                      (",", "piano.octave.down"), (".", "piano.octave.up"),
                      (">", "divider.left.inc"), ("<", "divider.left.dec"),
                      ("}", "divider.center.inc"), ("{", "divider.center.dec")]:
        @kb.add(_ch)
        def _(ev, _cmd=_cmd, _ch=_ch):
            if offer_to_overlay(_ch):
                return
            if state.overlay is None:
                do(_cmd)

    # tracker piano row: ZSXDCVGBHNJM plays the base octave chromatically.
    # (Lowercase d/m live here now; drone moved to D, motion to o.)
    for _key, _off in PIANO_TRACKER:
        @kb.add(_key)
        def _(ev, _off=_off, _key=_key):
            if offer_to_overlay(_key):
                return
            if state.overlay is None:
                do("piano.key", (_off, None))

    for _d in "123456789":
        @kb.add(_d)
        def _(ev, _d=_d):
            if offer_to_overlay(_d):
                return
            if state.overlay is None:
                do("pad.trigger-%02d" % int(_d))

    @kb.add("c-o")
    def _(ev):
        if not state.overlay:
            do("patch.open")

    @kb.add("c-s")
    def _(ev):
        if not state.overlay:
            do("patch.save")

    @kb.add("f4")
    def _(ev):
        if not state.overlay:
            do("patch.save-as")

    @kb.add("c-r")
    def _(ev):
        if not state.overlay:
            do("render.wav")

    @kb.add("c-h")
    def _(ev):
        do("panic")

    @kb.add("backspace")
    def _(ev):
        if state.overlay == "palette" and state.palette_filter:
            state.palette_filter = state.palette_filter[:-1]
            refresh()
        elif state.overlay == "input" and state.input_text:
            state.input_text = state.input_text[:-1]
            refresh()

    @kb.add(Keys.Any)
    def _(ev):
        # Catch-all for printable characters with no exact binding (they can
        # only reach overlay text entry). Exact bindings offer first (above).
        data = ev.data or ""
        offer_to_overlay(data)

    # custom config bindings (non-emergency only, validated at load)
    _cmd_ids = {c["id"] for c in COMMANDS}

    def _bind_custom(key, cmd):
        if cmd not in _cmd_ids:
            return

        @kb.add(key)
        def _(ev, _cmd=cmd, _key=key):
            if len(_key) == 1 and offer_to_overlay(_key):
                return
            if not state.overlay:
                do(_cmd)

    for _k, _c in (cfg.get("bindings") or {}).items():
        try:
            _bind_custom(_k, _c)
        except Exception:
            pass

    try:
        app_kwargs = dict(layout=Layout(FloatContainer(
            content=DynamicContainer(main_container),
            floats=[
            Float(content=ConditionalContainer(backdrop, Condition(overlay_visible)),
                  top=0, left=0, right=0, bottom=0),
            Float(content=ConditionalContainer(overlay_win, Condition(overlay_visible)),
                  top=2, left=4, right=4, height=22),
            ])), key_bindings=kb, style=style, mouse_support=bool(cfg["capabilities"]["mouse"]),
            full_screen=True)
        if app_input is not None:
            app_kwargs["input"] = app_input
        if app_output is not None:
            app_kwargs["output"] = app_output
        app = Application(**app_kwargs)
        app_ref["app"] = app
        app.run()
    except Exception as exc:
        # No genuine terminal (piped output, missing console, ...): match
        # mdbm's contract — interactive UI needs a real terminal, while
        # diagnostics / validation / snapshot / render stay non-interactive.
        if os.environ.get("PADSYNTH_DEBUG"):
            raise
        print("padsynth needs a genuine terminal (use Windows Terminal).")
        print("Without one: --diagnostics --snapshot 100x28 --render out.wav --validate-theme FILE")
        print("detail: %s" % exc)
        return 2
    finally:
        stop_playback()
    return 0


if __name__ == "__main__":
    sys.exit(main())







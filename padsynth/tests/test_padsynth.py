"""padsynth verification: patch graph, DSP, themes, config, parity, CLI paths."""
import copy
import importlib.util
import json
import math
import os

import pytest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location("padsynth", os.path.join(BASE, "padsynth.py"))
padsynth = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(padsynth)


def load_factory(pid):
    path = os.path.join(BASE, "patches", pid + ".json")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


FACTORY = ["weather-machine", "needle-rain", "ion-cell", "cyan-fog", "amber-strike"]
THEMES = ["neon-circuitry", "teal-core", "aqua-pink", "purpleblue-engine"]


# -- patch graph -------------------------------------------------------------

def test_factory_patches_validate():
    for pid in FACTORY:
        assert padsynth.validate_patch(load_factory(pid)) == [], pid


def test_patch_needs_output():
    bad = copy.deepcopy(padsynth.DEFAULT_PATCH)
    bad["nodes"] = [n for n in bad["nodes"] if n["type"] != "output"]
    assert any("output" in e for e in padsynth.validate_patch(bad))


@pytest.mark.parametrize("mut", [
    lambda p: p["nodes"].append({"id": "osc1", "type": "lfo",
                                 "params": {"rate_hz": 1.0, "shape": "sine"}}),  # duplicate id
    lambda p: p["nodes"].append({"id": "xx", "type": "frobnicator", "params": {}}),  # unknown type
    lambda p: p["nodes"][0]["params"].update({"frobnicate": 1}),  # unknown param
    lambda p: p["nodes"][0]["params"].update({"saw_mix": 99.0}),  # out of range
    lambda p: p["nodes"].append({"id": "zz", "type": "delay",
                                 "params": {"time_ms": 10.0, "feedback": 0.1,
                                            "mix": 0.1, "damp": 0.1},
                                 "inputs": {"in": "nope"}}),  # missing ref
])
def test_bad_patches_rejected(mut):
    bad = copy.deepcopy(padsynth.DEFAULT_PATCH)
    mut(bad)
    assert padsynth.validate_patch(bad), "mutation should fail validation"


def test_cycle_rejected():
    bad = copy.deepcopy(padsynth.DEFAULT_PATCH)
    bad["nodes"].append({"id": "loopa", "type": "chorus",
                          "params": {"rate": 0.5, "depth_ms": 2.0, "mix": 0.2},
                          "inputs": {"in": "loopb"}})
    bad["nodes"].append({"id": "loopb", "type": "chorus",
                          "params": {"rate": 0.5, "depth_ms": 2.0, "mix": 0.2},
                          "inputs": {"in": "loopa"}})
    errs = padsynth.validate_patch(bad)
    assert any("cycle" in e for e in errs)


def test_node_order_independent():
    patch = load_factory("ion-cell")
    rev = copy.deepcopy(patch)
    rev["nodes"] = list(reversed(rev["nodes"]))
    notes = padsynth.make_chord([45, 57], 0.5)
    a = padsynth.render_patch(patch, notes, 0.5, sr=8000, seed=3)
    b = padsynth.render_patch(rev, notes, 0.5, sr=8000, seed=3)
    assert a[0] == b[0] and a[1] == b[1]


# -- DSP ----------------------------------------------------------------------

@pytest.mark.parametrize("pid", FACTORY)
def test_render_deterministic_bounded(pid):
    patch = load_factory(pid)
    notes = padsynth.make_chord(padsynth.AUDITION_CHORD, 0.8)
    a = padsynth.render_patch(patch, notes, 0.8, sr=8000, seed=11)
    b = padsynth.render_patch(patch, notes, 0.8, sr=8000, seed=11)
    assert a[0] == b[0] and a[1] == b[1]
    for ch in a:
        assert len(ch) == 6400
        for v in ch:
            assert math.isfinite(v) and -1.0 <= v <= 1.0
    peak = padsynth.buffer_peak(a)
    assert 0.01 < peak <= 1.0, (pid, peak)


def test_render_seed_matters():
    patch = load_factory("cyan-fog")  # has audible air component
    notes = padsynth.make_chord([45], 0.5)
    a = padsynth.render_patch(patch, notes, 0.5, sr=8000, seed=1)
    b = padsynth.render_patch(patch, notes, 0.5, sr=8000, seed=2)
    assert a[0] != b[0]


def test_note_parsing():
    assert padsynth.note_to_midi("60") == 60
    assert padsynth.note_to_midi("C4") == 60
    assert padsynth.note_to_midi("Eb4") == 63
    assert padsynth.note_to_midi("F#2") == 42
    with pytest.raises(ValueError):
        padsynth.note_to_midi("H2")


def test_write_wav(tmp_path):
    patch = load_factory("needle-rain")
    notes = padsynth.make_chord([60], 0.4)
    stereo = padsynth.render_patch(patch, notes, 0.4, sr=8000, seed=5)
    dest = str(tmp_path / "t.wav")
    padsynth.write_wav(dest, stereo, 8000)
    assert os.path.getsize(dest) > 1000


# -- themes --------------------------------------------------------------------

def _catalog():
    return padsynth.discover_themes(["themes"], BASE)


def test_shipped_themes_valid():
    catalog = _catalog()
    for tid in THEMES:
        norm, errs, _warns = padsynth.load_theme_file(catalog[tid], catalog)
        assert norm is not None, (tid, errs)
        assert norm["id"] == tid


def test_unknown_theme_field_rejected(tmp_path):
    import tomllib
    catalog = _catalog()
    src = catalog["neon-circuitry"]
    with open(src, "rb") as fh:
        data = tomllib.load(fh)
    data["scripts"] = {"evil": True}
    dest = str(tmp_path / "evil.theme")
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write('schema = "md-editor-theme/1.1"\n')
    # validate mapping directly: unknown root field must fail
    errs, _w, norm = padsynth.validate_theme_mapping(data, source="evil")
    assert norm is None and any("unknown root field" in e for e in errs)


def test_failed_theme_keeps_current():
    catalog = _catalog()
    current, errs, _w = padsynth.load_theme_file(catalog["neon-circuitry"], catalog)
    assert current is not None
    before = dict(current)
    bad, errs2, _w2 = padsynth.load_theme_file(os.path.join(BASE, "padsynth.py"), catalog)
    assert bad is None and errs2
    assert current == before  # caller-side object untouched


def test_theme_slot_alias_warned():
    import copy
    catalog = _catalog()
    norm, _e, _w = padsynth.load_theme_file(catalog["neon-circuitry"], catalog)
    aliased = copy.deepcopy(norm)
    aliased["id"] = "alias-probe"
    for ly in aliased["layers"]:
        if ly.get("slot") == "tile.view.chrome":
            ly["slot"] = "tile.pads.chrome"
    errs, warns, out = padsynth.validate_theme_mapping(aliased, source="probe")
    assert out is not None and any("alias" in w for w in warns)


# -- config ---------------------------------------------------------------------

def test_config_missing_gives_defaults_with_diag(tmp_path):
    cfg, diags = padsynth.load_config(str(tmp_path / "nope.conf"))
    assert cfg["audio"]["sample_rate"] == 44100 and diags


def test_config_invalid_values_fall_back(tmp_path):
    dest = str(tmp_path / "bad.conf")
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write('schema = "padsynth-config/1.0"\n[audio]\nsample_rate = 5\n'
                 '[appearance]\nmotion = "warp"\n[bindings]\n"c-p" = "drone.toggle"\n')
    cfg, diags = padsynth.load_config(dest)
    assert cfg["audio"]["sample_rate"] == 44100
    assert cfg["appearance"]["motion"] == "normal"
    assert "c-p" not in cfg["bindings"]  # emergency route protected
    assert len(diags) >= 3


# -- parity / snapshot / cli ------------------------------------------------------

def test_parity_clean():
    assert padsynth.parity_report() == []


def test_snapshot_deterministic_sized():
    patch = load_factory("amber-strike")
    catalog = _catalog()
    norm, _e, _w = padsynth.load_theme_file(catalog["neon-circuitry"], catalog)
    a = padsynth.render_snapshot_text(patch, norm, 80, 20, seed=9)
    b = padsynth.render_snapshot_text(patch, norm, 80, 20, seed=9)
    assert a == b
    lines = a.split("\n")
    assert len(lines) == 20 and all(len(ln) == 80 for ln in lines)


def test_pad_chords_sane():
    for i in range(16):
        chord = padsynth.pad_chord(i)
        assert 3 <= len(chord) <= 4 and all(12 <= m <= 96 for m in chord)


# -- TUI state + commands (no terminal needed) ----------------------------------

def _tui_state(monkeypatch=None):
    cfg, _d = padsynth.load_config(os.path.join(BASE, "padsynth.conf"))
    catalog = _catalog()
    norm, _e, _w = padsynth.load_theme_file(catalog["neon-circuitry"], catalog)
    return padsynth.TuiState(cfg, copy.deepcopy(padsynth.DEFAULT_PATCH), None,
                             norm, "neon-circuitry", catalog,
                             os.path.join(BASE, "patches"), 7, 8000,
                             ("null", "offline"), {})


def test_tui_param_commands():
    st = _tui_state()
    st.param_sel = next(i for i, r in enumerate(padsynth.PARAM_ROWS) if r[0] == "flt.cutoff")
    before = padsynth._get_param(st.patch, "flt.cutoff")
    msg = padsynth.run_command(st, "param.inc")
    assert padsynth._get_param(st.patch, "flt.cutoff") != before and st.dirty
    padsynth.run_command(st, "param.reset")
    dflt = padsynth.patch_node_map(padsynth.DEFAULT_PATCH)["filt1"]["params"]["cutoff_hz"]
    assert padsynth._get_param(st.patch, "flt.cutoff") == dflt
    assert "CUTOFF" in msg.upper() or "cutoff" in msg.lower()


def test_tui_octave_vel_layout_quit():
    st = _tui_state()
    assert padsynth.run_command(st, "octave.up") == "pad octave +1"
    assert padsynth.run_command(st, "velocity.down") == "velocity 0.75"
    assert padsynth.run_command(st, "tile.toggle-mod") == "hide mod"
    assert "mod" in st.hidden
    assert padsynth.run_command(st, "layout.restore") == "tiles restored"
    assert not st.hidden
    assert padsynth.run_command(st, "quit.request") == "__quit__"
    st.dirty = True
    assert padsynth.run_command(st, "quit.request") == "unsaved changes"
    assert st.overlay == "confirm"


def test_tui_theme_next_rejects_gracefully(tmp_path):
    st = _tui_state()
    st.catalog = dict(st.catalog)
    st.catalog["broken"] = str(tmp_path / "missing.theme")
    msg = padsynth._apply_theme_by_id(st, "broken", commit=True)
    assert st.theme_id == "neon-circuitry" and "rejected" in msg


def test_cli_paths(capsys, tmp_path):
    assert padsynth.main(["--list-themes"]) == 0
    assert padsynth.main(["--list-patches"]) == 0
    catalog = _catalog()
    assert padsynth.main(["--validate-theme", catalog["neon-circuitry"]]) == 0
    assert padsynth.main(["--validate-theme", os.path.join(BASE, "padsynth.py")]) == 2
    assert padsynth.main(["--diagnostics"]) == 0
    assert padsynth.main(["needle-rain", "--snapshot", "60x12"]) == 0
    out = str(tmp_path / "cli.wav")
    assert padsynth.main(["needle-rain", "--render", out, "--seconds", "0.4",
                           "--sr", "8000", "--notes", "C3,Eb3,G3"]) == 0
    assert os.path.getsize(out) > 1000
    assert padsynth.main(["needle-rain", "--snapshot", "bad"]) == 2
    assert padsynth.main(["needle-rain", "--notes", "H2", "--render", out]) == 2
    capsys.readouterr()


def test_tui_builds_without_terminal(monkeypatch):
    pt = pytest.importorskip("prompt_toolkit")
    import argparse
    cfg, _d = padsynth.load_config(os.path.join(BASE, "padsynth.conf"))
    catalog = _catalog()
    norm, _e, _w = padsynth.load_theme_file(catalog["neon-circuitry"], catalog)
    built = {}

    class FakeApp:
        def __init__(self, *a, **k):
            built["keys"] = sorted(k)
            self.layout = k.get("layout")

        def run(self):
            # exercise a repaint path without a terminal
            self.layout.focus(self.layout.container)

        def invalidate(self):
            pass

        def exit(self):
            pass

    monkeypatch.setattr(pt, "Application", FakeApp)
    args = argparse.Namespace()
    rc = padsynth.run_tui(cfg, [], copy.deepcopy(padsynth.DEFAULT_PATCH), None,
                          norm, "neon-circuitry", catalog,
                          os.path.join(BASE, "patches"), 7, 8000,
                          ("null", "offline"), None, {}, args)
    assert rc == 0 and "layout" in built["keys"] and "style" in built["keys"]
    assert "mouse_support" in built["keys"]


def test_tui_pad_trigger_renders(monkeypatch):
    st = _tui_state()
    seen = {}

    def fake_audition(patch, notes, seconds, sr, seed, backend, loop=False, notify=None):
        seen["notes"] = notes
        return ([0.0], [0.0])

    monkeypatch.setattr(padsynth, "audition_async", fake_audition)
    msg = padsynth.run_command(st, "pad.trigger-01", 0.9)
    assert "pad 01" in msg and len(seen["notes"]) >= 3


# -- headless end-to-end: REAL Application, REAL key/SGR bytes -------------------
# Boots the full TUI with pipe input + dummy output (no console needed) and
# drives it with the exact bytes Windows Terminal would send.

def _e2e_config():
    cfg, _d = padsynth.load_config(os.path.join(BASE, "padsynth.conf"))
    # single-tile layout: pads span the full width, so click geometry is exact
    cfg["layout"]["pads_visible"] = True
    cfg["layout"]["voice_visible"] = False
    cfg["layout"]["mod_visible"] = False
    cfg["layout"]["browser_visible"] = False
    return cfg


def _e2e_run(monkeypatch, tmp_path, feed):
    pytest.importorskip("prompt_toolkit")
    from prompt_toolkit.input.defaults import create_pipe_input
    from prompt_toolkit.output.defaults import DummyOutput
    monkeypatch.chdir(tmp_path)
    cfg = _e2e_config()
    catalog = _catalog()
    norm, _e, _w = padsynth.load_theme_file(catalog["neon-circuitry"], catalog)
    import argparse
    with create_pipe_input() as inp:
        inp.send_text(feed)
        rc = padsynth.run_tui(cfg, [], copy.deepcopy(padsynth.DEFAULT_PATCH), None,
                              norm, "neon-circuitry", catalog,
                              os.path.join(BASE, "patches"), 7, 8000,
                              ("null", "offline"), None, {},
                              argparse.Namespace(),
                              app_input=inp, app_output=DummyOutput())
    return rc


def test_e2e_keyboard_triggers_pad(monkeypatch, tmp_path):
    seen = {}

    def fake_audition(patch, notes, seconds, sr, seed, backend, loop=False, notify=None):
        seen["notes"] = [n["midi"] for n in notes]
        if notify is not None:
            notify()

    monkeypatch.setattr(padsynth, "audition_async", fake_audition)
    rc = _e2e_run(monkeypatch, tmp_path, "5\x11")  # key 5, then CTRL+Q
    assert rc == 0
    assert seen["notes"] == padsynth.pad_chord(4, 0), seen


def test_e2e_mouse_click_triggers_pad(monkeypatch, tmp_path):
    seen = {}

    def fake_audition(patch, notes, seconds, sr, seed, backend, loop=False, notify=None):
        seen["notes"] = [n["midi"] for n in notes]
        seen["vel"] = [n["vel"] for n in notes]
        if notify is not None:
            notify()

    monkeypatch.setattr(padsynth, "audition_async", fake_audition)
    # SGR press+release at 1-based (41, 6): past the last pad cell, so the
    # toolkit snaps to the final content column; col clamps to 3 -> pad idx 11.
    press = "\x1b[<0;41;6M"
    release = "\x1b[<0;41;6m"
    rc = _e2e_run(monkeypatch, tmp_path, press + release + "\x11")
    assert rc == 0
    assert seen["notes"] == padsynth.pad_chord(11, 0), seen
    assert all(abs(v - (0.35 + 0.65 * 5 / 6)) < 0.01 for v in seen["vel"]), seen


def test_e2e_mouse_cell_geometry(monkeypatch, tmp_path):
    seen = {}

    def fake_audition(patch, notes, seconds, sr, seed, backend, loop=False, notify=None):
        seen.setdefault("hits", []).append(([n["midi"] for n in notes],
                                            round(notes[0]["vel"], 3)))

    monkeypatch.setattr(padsynth, "audition_async", fake_audition)
    # left edge of each pad cell at 1-based x = 2, 8, 14, 20 -> pads 9..12 vel min
    feed = "".join("\x1b[<0;%d;6M\x1b[<0;%d;6m" % (x, x) for x in (2, 8, 14, 20)) + "\x11"
    rc = _e2e_run(monkeypatch, tmp_path, feed)
    assert rc == 0
    assert [h[0] for h in seen["hits"]] == [padsynth.pad_chord(i, 0) for i in (8, 9, 10, 11)]
    assert all(abs(h[1] - 0.35) < 0.01 for h in seen["hits"]), seen


def _e2e_run_full(monkeypatch, tmp_path, feed):
    pytest.importorskip("prompt_toolkit")
    from prompt_toolkit.input.defaults import create_pipe_input
    from prompt_toolkit.output.defaults import DummyOutput
    monkeypatch.chdir(tmp_path)
    cfg, _d = padsynth.load_config(os.path.join(BASE, "padsynth.conf"))
    catalog = _catalog()
    norm, _e, _w = padsynth.load_theme_file(catalog["neon-circuitry"], catalog)
    import argparse
    with create_pipe_input() as inp:
        inp.send_text(feed)
        rc = padsynth.run_tui(cfg, [], copy.deepcopy(padsynth.DEFAULT_PATCH), None,
                              norm, "neon-circuitry", catalog,
                              os.path.join(BASE, "patches"), 7, 8000,
                              ("null", "offline"), None, {},
                              argparse.Namespace(),
                              app_input=inp, app_output=DummyOutput())
    return rc


def test_e2e_full_layout_paints_and_overlays(monkeypatch, tmp_path):
    # all four tiles visible: Tab cycles, palette opens/filters/dismisses,
    # help opens, then quit. Proves full-layout paint + overlay floats.
    rc = _e2e_run_full(monkeypatch, tmp_path, "\t\x10dr\x1b\x11")
    assert rc == 0


def test_e2e_slider_click_reaches_sound(monkeypatch, tmp_path):
    seen = {}

    def fake_audition(patch, notes, seconds, sr, seed, backend, loop=False, notify=None):
        filt = padsynth.patch_node_map(patch)["filt1"]["params"]["cutoff_hz"]
        seen["cutoff"] = filt
        seen["notes"] = [n["midi"] for n in notes]
        if notify is not None:
            notify()

    monkeypatch.setattr(padsynth, "audition_async", fake_audition)
    pytest.importorskip("prompt_toolkit")
    from prompt_toolkit.input.defaults import create_pipe_input
    from prompt_toolkit.output.defaults import DummyOutput
    monkeypatch.chdir(tmp_path)
    cfg, _d = padsynth.load_config(os.path.join(BASE, "padsynth.conf"))
    cfg["layout"]["pads_visible"] = False
    cfg["layout"]["voice_visible"] = True
    cfg["layout"]["mod_visible"] = False
    cfg["layout"]["browser_visible"] = False
    catalog = _catalog()
    norm, _e, _w = padsynth.load_theme_file(catalog["neon-circuitry"], catalog)
    import argparse
    # voice-only layout: flt.cutoff is row 7 -> 1-based y = 3 + 7 + 1 = 11.
    # far-right x pins the log slider to its 18000 Hz maximum.
    # (the click dirties the patch, so quit needs a discard afterwards)
    with create_pipe_input() as inp:
        inp.send_text("\x1b[<0;70;11M\x1b[<0;70;11m5\x11d")
        rc = padsynth.run_tui(cfg, [], copy.deepcopy(padsynth.DEFAULT_PATCH), None,
                              norm, "neon-circuitry", catalog,
                              os.path.join(BASE, "patches"), 7, 8000,
                              ("null", "offline"), None, {},
                              argparse.Namespace(),
                              app_input=inp, app_output=DummyOutput())
    assert rc == 0
    assert seen["cutoff"] == 18000.0, seen
    assert seen["notes"] == padsynth.pad_chord(4, 0), seen


# -- demo mode ---------------------------------------------------------------

def test_medley_deterministic():
    kw = dict(patch_dir=os.path.join(BASE, "patches"), sr=8000, seed=5,
              seconds_each=0.4)
    (l1, r1), _sr, manifest = padsynth.build_medley(**kw)
    (l2, r2), _sr2, manifest2 = padsynth.build_medley(**kw)
    assert manifest == manifest2 and len(manifest) == 5
    assert [m[0] for m in manifest] == ["weather-machine", "needle-rain", "ion-cell",
                                        "cyan-fog", "amber-strike"]
    assert l1 == l2 and r1 == r2
    assert len(l1) == 3200 * 5 - 1200 * 4
    import math
    for v in l1 + r1:
        assert math.isfinite(v) and -1.0 <= v <= 1.0
    assert 0.05 < padsynth.buffer_peak((l1, r1)) <= 1.0


def test_medley_missing_patch_fails(tmp_path):
    with pytest.raises(ValueError):
        padsynth.build_medley(str(tmp_path), sr=8000, seed=5, seconds_each=0.4)


def test_cli_demo(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert padsynth.main(["--demo", "--sr", "8000"]) == 0
    out = tmp_path / "demo-medley.wav"
    assert out.stat().st_size > 1000
    text = capsys.readouterr().out
    assert "PADSYNTH DEMO" in text and "weather-machine" in text


def test_cli_demo_play_null(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(padsynth, "probe_audio", lambda _prefer: ("null", "offline"))
    assert padsynth.main(["--demo-play", "--sr", "8000"]) == 0
    text = capsys.readouterr().out
    assert "unavailable" in text


def test_tui_demo_medley_plays(monkeypatch):
    st = _tui_state()
    played = {}

    def fake_play(stereo, sr, backend, loop=False, notify=None):
        played["n"] = len(stereo[0])
        played["sr"] = sr
        if notify is not None:
            notify()

    monkeypatch.setattr(padsynth, "play_buffer_async", fake_play)
    msg = padsynth.run_command(st, "demo.medley")
    assert "medley" in msg
    import time
    for _ in range(200):
        if "n" in played:
            break
        time.sleep(0.1)
    assert played.get("n") == 14400 * 5 - 1200 * 4, played
    assert played.get("sr") == 8000


# -- piano keyboard ------------------------------------------------------------

def test_piano_geometry_units():
    p = padsynth
    assert p.piano_white_midi(60, 0) == 60
    assert p.piano_white_midi(60, 13) == 83
    assert p.piano_key_at(60, 12, 1) == (64, False)   # white E, gradient row
    assert p.piano_key_at(60, 5, 0) == (61, True)     # black C#
    assert p.piano_key_at(60, 5, 7) == (62, False)    # low click finds white D
    assert p.piano_key_at(60, 12, 7) == (64, False)   # white E, safe zone
    assert p.piano_key_at(60, 14, 0) == (64, False)   # E edge col: still white
    assert p.piano_key_at(60, 15, 0) == (65, False)   # E-F boundary: no black
    assert abs(p.piano_velocity(0) - 0.475) < 1e-9
    assert p.piano_velocity(3) == 1.0
    for y in (4, 5, 6, 7):
        assert p.piano_velocity(y) == 1.0, y


def test_piano_commands(monkeypatch):
    st = _tui_state()
    seen = {}

    def fake_audition(patch, notes, seconds, sr, seed, backend, loop=False, notify=None):
        seen["midi"] = notes[0]["midi"]
        seen["vel"] = notes[0]["vel"]
        if notify is not None:
            notify()

    monkeypatch.setattr(padsynth, "audition_async", fake_audition)
    assert padsynth.run_command(st, "piano.key", None) == "C4 vel 0.80"
    assert (seen["midi"], seen["vel"]) == (60, 0.8)
    assert 60 in st.piano_hot
    assert padsynth.run_command(st, "piano.key", (3, 0.5)) == "D#4 vel 0.50"
    assert (seen["midi"], seen["vel"]) == (63, 0.5)
    assert padsynth.run_command(st, "piano.octave.down") == "piano C3"
    st.piano_base = 24
    assert padsynth.run_command(st, "piano.octave.down") == "piano C1"
    st.piano_base = 72
    assert padsynth.run_command(st, "piano.octave.up") == "piano C5"
    assert padsynth.run_command(st, "tile.focus-5") == "focus piano"
    assert padsynth.run_command(st, "tile.toggle-piano") == "hide piano"
    assert padsynth.run_command(st, "tile.toggle-piano") == "show piano"


def test_e2e_tracker_keyboard(monkeypatch, tmp_path):
    seen = {}

    def fake_audition(patch, notes, seconds, sr, seed, backend, loop=False, notify=None):
        seen.setdefault("midis", []).append(notes[0]["midi"])
        if notify is not None:
            notify()

    monkeypatch.setattr(padsynth, "audition_async", fake_audition)
    rc = _e2e_run(monkeypatch, tmp_path, "zs\x11")  # C, C#, then CTRL+Q
    assert rc == 0
    assert seen["midis"] == [60, 61], seen


def _e2e_run_piano_only(monkeypatch, tmp_path, feed):
    pytest.importorskip("prompt_toolkit")
    from prompt_toolkit.input.defaults import create_pipe_input
    from prompt_toolkit.output.defaults import DummyOutput
    monkeypatch.chdir(tmp_path)
    cfg, _d = padsynth.load_config(os.path.join(BASE, "padsynth.conf"))
    for key in ("pads_visible", "voice_visible", "mod_visible", "browser_visible"):
        cfg["layout"][key] = False
    catalog = _catalog()
    norm, _e, _w = padsynth.load_theme_file(catalog["neon-circuitry"], catalog)
    import argparse
    with create_pipe_input() as inp:
        inp.send_text(feed)
        rc = padsynth.run_tui(cfg, [], copy.deepcopy(padsynth.DEFAULT_PATCH), None,
                              norm, "neon-circuitry", catalog,
                              os.path.join(BASE, "patches"), 7, 8000,
                              ("null", "offline"), None, {},
                              argparse.Namespace(),
                              app_input=inp, app_output=DummyOutput())
    return rc


def test_e2e_piano_mouse_white_black_safe(monkeypatch, tmp_path):
    seen = {}

    def fake_audition(patch, notes, seconds, sr, seed, backend, loop=False, notify=None):
        seen.setdefault("hits", []).append((notes[0]["midi"], round(notes[0]["vel"], 3)))
        if notify is not None:
            notify()

    monkeypatch.setattr(padsynth, "audition_async", fake_audition)
    # piano-only layout on the 80x40 headless screen: the empty tile slot
    # fills the middle, so the bottom-docked piano frame sits at rows 29-38
    # and its content at rows 30-37 (1-based 31-38).
    # (14,32): white E4, gradient vel 0.65. (7,31): black C#4, vel 0.475.
    # (14,38): white E4 in the safe zone, vel 1.0.
    feed = ("\x1b[<0;14;32M\x1b[<0;14;32m"
            "\x1b[<0;7;31M\x1b[<0;7;31m"
            "\x1b[<0;14;38M\x1b[<0;14;38m\x11")
    rc = _e2e_run_piano_only(monkeypatch, tmp_path, feed)
    assert rc == 0
    assert [h[0] for h in seen["hits"]] == [64, 61, 64], seen
    assert abs(seen["hits"][0][1] - 0.65) < 0.01, seen
    assert abs(seen["hits"][1][1] - 0.475) < 0.01, seen
    assert seen["hits"][2][1] == 1.0, seen


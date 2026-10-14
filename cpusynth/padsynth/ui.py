"""PadSynth TUI - a mouse-first canvas over prompt_toolkit.

One full-screen ``FormattedTextControl`` is repainted on every invalidate; all
geometry, hit-testing, hover, focus, drag and animation run here. This gives the
mdbm "fixed character-cell grid, occupancy only" aesthetic seen in the reference
HTML files, and mouse works in Windows Terminal through VT mouse reporting.
"""
from __future__ import annotations

import math
import threading
import time

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.mouse_events import MouseButton, MouseEventType

from .param import BY_KEY, PARAMS, group_of, list_presets, save_preset
from .themes import Skin, list_themes
from .util import clamp, fmt_hz, fmt_time, midi_to_name

SCREENS = ("PLAY", "PATCH", "MIX", "LIBRARY")

_VEL_ROWS = 4  # bottom keyboard rows that always play at 100% velocity

# Physical-keyboard note piano: each row triggers chromatic notes (base 48)
# at a fixed velocity. Pressed keys are gates: auto-release after _KBD_HOLD s
# because terminals send no key-up.
_KBD_ROWS = ("qwertyuiop[]", "asdfghjkl;'", "zxcvbnm,./")
_KBD_VEL = (0.4, 0.7, 1.0)
_KBD_HOLD = 0.4
_KBD_INDEX: dict[str, int] = {}
for _r, _row in enumerate(_KBD_ROWS):
    for _i, _ch in enumerate(_row):
        _KBD_INDEX[_ch] = _r * 12 + _i

CHORD_SETS = {
    "MIN": {
        "i": [0, 3, 7, 10, 14], "ii": [0, 3, 7, 10], "III": [0, 4, 7, 11, 15],
        "iv": [0, 3, 7, 10], "v": [0, 3, 7, 10, 14], "VI": [0, 4, 7, 11, 15],
        "VII": [0, 2, 7, 12, 14], "v7": [0, 3, 7, 10, 14],
    },
    "MAJ": {
        "I": [0, 4, 7, 11, 15], "ii": [0, 3, 7, 10], "iii": [0, 3, 7, 10, 14],
        "IV": [0, 4, 7, 11, 15], "V": [0, 4, 7, 11, 14], "vi": [0, 3, 7, 10, 14],
        "VII": [0, 2, 7, 12, 14], "III7": [0, 4, 7, 10, 15],
    },
    "DOR": {
        "i": [0, 3, 7, 10, 14], "ii": [0, 3, 7, 10], "III": [0, 4, 7, 11, 15],
        "IV": [0, 4, 7, 11, 14], "v": [0, 3, 7, 10, 14], "vi": [0, 4, 7, 11, 15],
        "VII": [0, 2, 7, 12, 14], "IV7": [0, 4, 7, 10, 14],
    },
}
_SCALE_DEGREES = ("i", "ii", "III", "iv", "v", "VI", "VII", "v7")
_SCALE_DEGREES_MAJ = ("I", "ii", "iii", "IV", "V", "vi", "VII", "III7")
DEG_LABELS = {"MIN": _SCALE_DEGREES, "MAJ": _SCALE_DEGREES_MAJ, "DOR": _SCALE_DEGREES}


def to01(spec, v):
    if spec.log:
        return clamp(math.log(v / spec.lo) / math.log(spec.hi / spec.lo), 0.0, 1.0)
    return clamp((v - spec.lo) / (spec.hi - spec.lo), 0.0, 1.0)


def from01(spec, t):
    t = clamp(t, 0.0, 1.0)
    if spec.log:
        return spec.lo * (spec.hi / spec.lo) ** t
    return spec.lo + (spec.hi - spec.lo) * t


class _Shim:
    """Pseudo-spec for the morph / macro faders."""

    def __init__(self, lo, hi, log=False):
        self.lo, self.hi, self.log = lo, hi, log


class _Ctx:
    """Cell-rasterized canvas: every draw lands in a 2D cell grid, so full-width
    background fills can never push later text off the right edge."""

    def __init__(self, w: int, h: int):
        self.w = w
        self.h = h
        self._chars: list[list[str]] = [[" "] * w for _ in range(h)]
        self._sty: list[list[str]] = [[""] * w for _ in range(h)]
        self.hits: list[tuple] = []

    def put(self, x: int, y: int, style: str, text: str):
        if y < 0 or y >= self.h or x < 0 or x >= self.w or not text:
            return
        for dx, ch in enumerate(text):
            cx = x + dx
            if cx >= self.w:
                break
            if cx < 0:
                continue
            self._chars[y][cx] = ch
            self._sty[y][cx] = style

    def fill(self, x: int, y: int, w: int, h: int, style: str, ch: str = " "):
        w = max(0, min(w, self.w - x))
        x = max(0, x)
        for yy in range(max(0, y), min(y + h, self.h)):
            self.put(x, yy, style, ch * w)

    def hline(self, x: int, y: int, w: int, style: str, ch: str):
        self.fill(x, y, w, 1, style, ch)

    def box(self, x: int, y: int, w: int, h: int, style: str, chs: str = "┌┐└┘─│"):
        if w < 3 or h < 3:
            self.fill(x, y, w, h, style, "-")
            return
        tl, tr, bl, br, hz, vt = chs
        self.hline(x + 1, y, w - 2, style, hz)
        self.hline(x + 1, y + h - 1, w - 2, style, hz)
        self.put(x, y, style, tl)
        self.put(x + w - 1, y, style, tr)
        self.put(x, y + h - 1, style, bl)
        self.put(x + w - 1, y + h - 1, style, br)
        for yy in range(y + 1, y + h - 1):
            self.put(x, yy, style, vt)
            self.put(x + w - 1, yy, style, vt)

    def hit(self, x: int, y: int, w: int, h: int, tag: str, payload):
        self.hits.append((x, y, w, h, tag, payload))

    def fragments(self) -> list:
        out: list = []
        for y in range(self.h):
            row: list[tuple] = []
            cur_sty, run = "", ""
            for x in range(self.w):
                st = self._sty[y][x]
                if st == cur_sty:
                    run += self._chars[y][x]
                else:
                    if run:
                        row.append((cur_sty, run))
                    cur_sty, run = st, self._chars[y][x]
            if run:
                row.append((cur_sty, run))
            out.extend(row)
            out.append(("", "\n"))
        return out[:-1]


class _CanvasControl(FormattedTextControl):
    """FormattedTextControl that routes terminal mouse events to the app."""

    def __init__(self, owner):
        super().__init__(focusable=False, show_cursor=False)
        self._owner = owner

    def mouse_handler(self, mouse_event):
        return self._owner._on_mouse(mouse_event)


class PadSynthApp:
    def __init__(self, engine, patch, skin: Skin, midi, demo, args, output=None):
        self.engine = engine
        self.patch = patch
        self.skin = skin
        self.midi = midi
        self.demo = demo
        self.args = args

        self.screen = "PLAY"
        self.scale = "MIN"
        self.root = 45
        self.mode = "MOM"
        self.octave = 0
        self.macro = [0.0, 0.0, 0.0, 0.0]
        self.morph = patch.morph
        self.message = ""
        self.message_t = 0.0

        self.active_pads: set[int] = set()
        self.key_lit: set[int] = set()
        self.kbd_events: dict[int, threading.Event] = {}
        self.arp_stop: dict[int, threading.Event] = {}
        self.drag: dict | None = None
        self.press: dict | None = None
        self.hover: tuple | None = None
        self._keygeom = (2, 2, 0, 0, 0, 0)
        self._pending_hits: list = []

        self.sel_preset = 0
        self.sel_theme = 0
        self.theme_preview: Skin | None = None
        self.input_mode = False
        self.input_buf = ""
        self.focus_id: tuple | None = None
        self._running = True

        self.control = _CanvasControl(self)
        self.app = Application(
            layout=Layout(Window(self.control, always_hide_cursor=True)),
            key_bindings=self._build_keys(),
            mouse_support=True,
            full_screen=True,
            output=output,
        )
        self._push_live()
        threading.Thread(target=self._refresh_loop, daemon=True).start()

    # ---- live patch plumbing -----------------------------------------
    def _push_live(self):
        self.patch.morph = self.morph
        live = self.patch.live(self.macro)
        self.engine.set_params(live)

    def set_param(self, key: str, value: float):
        spec = BY_KEY[key]
        value = float(clamp(value, spec.lo, spec.hi))
        self.patch.touch(key, value)
        self._push_live()

    def change_param(self, key: str, delta: float):
        spec = BY_KEY[key]
        if self.morph <= 0.5:
            v = self.patch.a[key]
        else:
            v = self.patch.b[key]
        if spec.log:
            v = v * (1.0 + delta) if delta >= 0 else v / (1.0 - delta)
        else:
            v = v + delta
        self.set_param(key, v)

    def notify(self, msg: str):
        self.message = msg
        self.message_t = time.monotonic()

    def set_octave(self, delta: int):
        self.octave = clamp(self.octave + delta, -3, 3)
        self.engine.push("transpose", self.octave * 12)
        self.notify(f"OCTAVE {self.octave:+d}")

    # ---- rendering ------------------------------------------------------
    def _render(self):
        size = self.app.output.get_size()
        W, H = size.columns, size.rows
        W = max(20, W)
        H = max(14, H)
        ctx = _Ctx(W, H)
        ctx.fill(0, 0, W, H, self.skin.style("background"))
        self._draw_header(ctx, W)
        self._draw_nav(ctx, W)
        self._draw_divider(ctx, W)
        if self.screen == "PLAY":
            self._draw_play(ctx, W, H)
        elif self.screen == "PATCH":
            self._draw_patch(ctx, W, H)
        elif self.screen == "MIX":
            self._draw_mix(ctx, W, H)
        else:
            self._draw_library(ctx, W, H)
        self._draw_macros(ctx, W, H)
        self._draw_footer(ctx, W, H)
        self._pending_hits = ctx.hits
        self.control.text = ctx.fragments()

    def _render_frame_error(self):
        try:
            size = self.app.output.get_size()
            W = max(20, size.columns)
            H = max(14, size.rows)
        except Exception:
            W, H = 80, 24
        ctx = _Ctx(W, H)
        ctx.fill(0, 0, W, H, self.skin.style("background"))
        msg = getattr(self, "_frame_error", "render error")
        ctx.put(4, H // 2 - 3, self.skin.style("title"), " ! render failed")
        ctx.put(4, H // 2 - 1, self.skin.style("status_warn"), ("  " + msg)[: W - 8])
        ctx.put(4, H // 2 + 1, self.skin.style("muted"),
                "  see terminal stderr · press q to quit")
        self.control.text = ctx.fragments()

    def _draw_header(self, ctx, W):
        sk = self.skin
        st = sk.style("title")
        ctx.put(0, 0, st, " PADSYNTH 020")
        right = (f"ENG {self.engine.cpu * 100:4.0f}%  N {self.engine.note_count:2d}  "
                 f"OCT {self.octave:+d}  DEMO {'ON ' if self.demo.running else 'OFF'}")
        ctx.put(W - len(right) - 2, 0, sk.style("status_ok" if self.demo.running else "muted"), right)

    def _draw_nav(self, ctx, W):
        sk = self.skin
        x = 2
        for s in SCREENS:
            if s == self.screen:
                style = sk.style("sel")
            elif self.hover and self.hover[0] == "nav" and self.hover[1] == s:
                style = sk.style("hover")
            else:
                style = sk.style("key")
            ctx.put(x, 1, style, f" {s} ")
            ctx.hit(x, 1, len(s) + 2, 1, "nav", s)
            x += len(s) + 4
        midi_txt = f"MIDI {self.midi.port_name}" if (self.midi and self.midi.port_name) else "MIDI --"
        ctx.put(x, 1, sk.style("muted"), "  " + midi_txt)
        skt = f"SKIN {self.skin.name}"
        ctx.put(W - len(skt) - 3, 1, sk.style("muted"), skt)

    def _draw_divider(self, ctx, W):
        sk = self.skin
        ch = sk.glyph("divider") or "-"
        for c in range(W):
            lvl = (c % 7) / 7.0
            ctx.put(c, 2, sk.style("border") + f" fg:{sk.ramp_hex('divider', lvl)}", ch)

    # ---- PLAY -----------------------------------------------------------
    def _draw_play(self, ctx, W, H):
        sk = self.skin
        top = 4
        degs = DEG_LABELS[self.scale]
        pad_w = 13
        pad_h = 2
        gap = 1
        for r in range(4):
            for c in range(4):
                idx = r * 4 + c
                x = 2 + c * (pad_w + gap)
                y = top + r * (pad_h + gap)
                hot = idx in self.active_pads
                style = sk.style("pad_hot" if hot else "pad")
                ctx.box(x, y, pad_w, pad_h, style)
                deg = degs[c]
                root_name = midi_to_name(self.root + [-12, 0, 12, 24][r])
                octv = ["-1", "", "+1", "+2"][r]
                ctx.put(x + 1, y, style, f"{root_name}  {deg}")
                ctx.put(x + 1, y + 1, sk.style("muted"), f"{'x' if hot else '.'}{octv}" + " " * 5)
                ctx.hit(x, y, pad_w, pad_h, "pad", idx)

        rx = 2 + 4 * (pad_w + gap) + 3
        ctx.put(rx, top, sk.style("heading"), "SCALE")
        for i, name in enumerate(("MIN", "MAJ", "DOR")):
            sx = rx + 6 * i
            st = sk.style("sel") if self.scale == name else sk.style("key")
            ctx.put(sx, top + 1, st, f" {name}")
            ctx.hit(sx, top + 1, 6, 1, "scale", name)
        ctx.put(rx, top + 3, sk.style("heading"), "ROOT")
        for i in range(12):
            syx = rx + (i % 6) * 6
            sy = top + 4 + i // 6
            st = sk.style("sel") if (self.root - 45 + 60) % 12 == i else sk.style("key")
            ctx.put(syx, sy, st, f" {midi_to_name(60 + i)}")
            ctx.hit(syx, sy, 6, 1, "root", i)
        ctx.put(rx, top + 7, sk.style("heading"), "MODE")
        for i, name in enumerate(("HOLD", "MOM", "ARP")):
            sx = rx + 6 * i
            st = sk.style("sel") if self.mode == name else sk.style("key")
            ctx.put(sx, top + 8, st, f" {name}")
            ctx.hit(sx, top + 8, 6, 1, "mode", name)

        self._draw_transport(ctx, W, H)
        self._draw_keys(ctx, W, H)

    def _draw_transport(self, ctx, W, H):
        sk = self.skin
        ty = H - 5
        ctx.put(2, ty, sk.style("heading"), "DEMO")
        st = sk.style("sel") if self.demo.running else sk.style("key")
        ctx.put(2, ty + 1, st, " [ON] ")
        ctx.hit(2, ty + 1, 6, 1, "demo", 1)
        ctx.put(10, ty, sk.style("heading"), "LOOP")
        ctx.put(10, ty + 1, sk.style("meta"), f" {'<'} {self.demo.pattern_name} {'>'}")
        ctx.hit(10, ty + 1, 8, 1, "pat", -1)
        ctx.hit(10 + 8 + len(self.demo.pattern_name), ty + 1, 4, 1, "pat", 1)
        chd = f" {self.demo.chord_name} "
        ctx.put(30, ty + 1, sk.style("text") if self.demo.running else sk.style("muted"), chd)
        ctx.put(30, ty, sk.style("heading"), "CHORD")
        # octave
        ctx.put(W - 22, ty, sk.style("heading"), "OCTAVE")
        ctx.put(W - 22, ty + 1, sk.style("key"), " [ - ] ")
        ctx.hit(W - 22, ty + 1, 7, 1, "oct", -1)
        ctx.put(W - 12, ty + 1, sk.style("text"), f"{self.octave:+d}")
        ctx.put(W - 22, ty + 2, sk.style("key"), " [ + ] ")
        ctx.hit(W - 22, ty + 2, 7, 1, "oct", 1)

    def _draw_keys(self, ctx, W, H):
        sk = self.skin
        zone_bottom = H - 6                     # transport row sits at H - 5
        body_top = 15                           # just below the pad grid
        rows = min(7, zone_bottom - body_top + 1)
        safe = min(_VEL_ROWS, rows)
        if rows < 5:                            # tiny terminals: shrink up
            body_top = zone_bottom - 4 + 1
            rows = min(4, max(2, zone_bottom - body_top + 1))
            safe = min(_VEL_ROWS, rows)
        note0 = 36
        maxkeys = (W - 4) // 2
        nkeys = min(29, max(12, maxkeys))
        key_w = max(2, (W - 4) // nkeys)
        self._keygeom = (2, key_w, note0, nkeys, body_top, rows)
        ctx.put(2, body_top - 1, sk.style("heading"), "KEYS")
        ctx.put(25, body_top - 1, sk.style("meta"),
                "qwe/asd/zxc 40/70/100% · bottom 4 key rows = 100% vel")
        boundary = body_top + rows - safe       # first 100%-velocity row
        b_h = max(2, min(round(rows * 0.4), max(1, rows - safe)))
        for i in range(nkeys):
            x = 2 + i * key_w
            midi = note0 + i
            black = (midi % 12) in (1, 3, 6, 8, 10)
            lit = midi in self.key_lit
            if black:
                st_lit = sk.style("focus")
                ctx.fill(x, body_top, key_w, b_h, st_lit if lit else sk.style("key"))
            else:
                st = sk.style("pad_hot" if lit else "pad")
                ctx.fill(x, body_top, key_w, rows, st)
                if boundary > body_top:
                    ctx.fill(x, boundary, key_w, 1, sk.style("border"))
                ctx.put(x, body_top + rows - 1, sk.style("muted"), midi_to_name(midi)[0])
            ctx.hit(x, body_top, max(1, key_w), rows, "key", midi)

    # ---- PATCH ----------------------------------------------------------
    def _draw_patch(self, ctx, W, H):
        sk = self.skin
        y = 4
        self._draw_morph(ctx, W, y)
        y += 3
        cols = [
            ("VOICE", ("osc.wave", "osc.unison", "osc.detune", "osc.semis", "osc.fine", "osc.sub", "osc.noise")),
            ("FILTER", ("filter.mode", "filter.cut", "filter.res", "filter.envd", "filter.key")),
            ("ENV A", ("amp.a", "amp.d", "amp.s", "amp.r", "amp.vel")),
            ("ENV F", ("flt.a", "flt.d", "flt.s", "flt.r", "flt.amt")),
            ("LFO", ("l1.rate", "l1.wave", "l1.tgt", "l1.dep", "l2.rate", "l2.wave", "l2.tgt", "l2.dep")),
            ("PAN", ("pan.base", "pan.spread")),
        ]
        ncol = 4 if W < 110 else 6
        shown = cols if W >= 90 else cols[:4]
        cw = max(16, (W - 4 - 2 * (len(shown) - 1)) // len(shown))
        x = 2
        for name, keys in shown:
            self._draw_panel(ctx, x, y, cw, name, keys)
            x += cw + 2

    def _draw_morph(self, ctx, W, y):
        sk = self.skin
        ctx.put(2, y, sk.style("heading"), "MORPH-A")
        fw = min(22, (W - 40) // 2)
        self._draw_fader(ctx, 10, y, fw, _Shim(0.0, 1.0), self.morph, "morph", None)
        ctx.put(10 + fw + 2, y, sk.style("heading"), "B")
        ctx.put(10 + fw + 5, y, sk.style("key"), " A>B ")
        ctx.hit(10 + fw + 5, y, 5, 1, "copy", 1)
        ctx.put(10 + fw + 11, y, sk.style("key"), " B>A ")
        ctx.hit(10 + fw + 11, y, 5, 1, "copy", -1)
        ctx.put(W - 30, y, sk.style("heading"), "CHAR")
        for i, c in enumerate(("PAD", "STR", "AIR", "AMB")):
            sx = W - 28 + 6 * i
            st = sk.style("sel") if self.patch.char == c.lower()[:3] else sk.style("key")
            ctx.put(sx, y, st, f" {c}")
            ctx.hit(sx, y, 6, 1, "char", c)

    def _draw_panel(self, ctx, x, y, w, title, keys):
        sk = self.skin
        n = len(keys)
        w = max(14, w)
        ctx.box(x, y, w, n + 2, sk.style("border"))
        ctx.put(x + 1, y, sk.style("title"), f" {title} ")
        fw = max(5, w - 15)
        live = self.patch.live(self.macro)
        for i, k in enumerate(keys):
            spec = BY_KEY[k]
            py = y + 1 + i
            focused = self.focus_id == ("param", k)
            st = sk.style("focus") if focused else sk.style("meta")
            ctx.put(x + 1, py, st, f" {spec.label[:5]:<5}")
            self._draw_fader(ctx, x + 7, py, fw, spec, live[k], "param", k)
            ctx.put(x + 7 + fw + 1, py, sk.style("text"), self._fmt(spec, live[k]))

    def _fmt(self, spec, v):
        if spec.fmt:
            try:
                return spec.fmt(v)
            except Exception:
                pass
        if spec.unit == "hz":
            return fmt_hz(v)
        if spec.unit == "s":
            return fmt_time(v)
        return f"{v:.2f}"

    def _draw_fader(self, ctx, x, y, w, spec, value, tag, payload):
        sk = self.skin
        w = max(4, w)
        t = to01(spec, value)
        fill = int(round(t * (w - 2)))
        fill = max(0, min(w - 2, fill))
        pressed = self.drag is not None and self.drag.get("payload") == payload and self.drag.get("tag") == tag
        st_fill = sk.style("press" if pressed else "bar")
        ctx.hit(x, y, w, 1, tag, payload)
        ctx.put(x, y, sk.style("border"), "[")
        if fill > 0:
            ctx.put(x + 1, y, st_fill, "=" * fill)
        ctx.put(x + 1 + fill, y, sk.style("cursor"), "I")
        rest = w - 2 - fill - 1
        if rest > 0:
            ctx.put(x + 2 + fill, y, sk.style("bar_empty"), "-" * rest)
        ctx.put(x + w - 1, y, sk.style("border"), "]")

    # ---- MIX ------------------------------------------------------------
    def _draw_mix(self, ctx, W, H):
        sk = self.skin
        y = 4
        panels = [
            ("CHORUS", ("fx.chorus.mix", "fx.chorus.rate", "fx.chorus.depth")),
            ("DELAY", ("fx.delay.time", "fx.delay.fb", "fx.delay.mix")),
            ("REVERB", ("fx.reverb.size", "fx.reverb.damp", "fx.reverb.mix")),
            ("MASTER", ("master.level", "master.drive")),
        ]
        cw = max(16, (W - 6) // 2)
        for i, (name, keys) in enumerate(panels):
            self._draw_panel(ctx, 2 + (i % 2) * (cw + 2), y + (i // 2) * 7, cw, name, keys)

        my = H - 7
        ctx.put(2, my, sk.style("heading"), "OUT L")
        ctx.put(2, my + 1, sk.style("heading"), "OUT R")
        mw = W - 13
        for c in range(mw):
            st = sk.style("bar") if c / max(1, mw) < self.engine.meter_l else sk.style("bar_empty")
            ctx.put(10 + c, my, st, " ")
            st = sk.style("bar") if c / max(1, mw) < self.engine.meter_r else sk.style("bar_empty")
            ctx.put(10 + c, my + 1, st, " ")

    # ---- LIBRARY ----------------------------------------------------------
    def _draw_library(self, ctx, W, H):
        sk = self.skin
        presets = list_presets()
        themes = list_themes()
        hw = max(20, W // 2)
        ctx.put(2, 4, sk.style("title"), " PRESETS ")
        ctx.put(2, 5, sk.style("muted"), f" {len(presets)} files in presets/")
        for i, p in enumerate(presets):
            if i >= 12:
                break
            st = sk.style("sel") if i == self.sel_preset else sk.style("input")
            ctx.put(2, 6 + i, st, f"  {p.stem}")
            ctx.hit(2, 6 + i, hw - 3, 1, "preset", i)
        ctx.put(hw, 4, sk.style("title"), " THEMES ")
        ctx.put(hw, 5, sk.style("muted"), f" {len(themes)} skins in themes/")
        for i, t in enumerate(themes):
            if i >= 12:
                break
            st = sk.style("sel") if i == self.sel_theme else sk.style("input")
            ctx.put(hw, 6 + i, st, f"  {t.stem}")
            ctx.hit(hw, 6 + i, hw - 4, 1, "theme", i)
        ay = H - 7
        ctx.put(2, ay, sk.style("key"), " LOAD ")
        ctx.hit(2, ay, 6, 1, "load", 1)
        ctx.put(9, ay, sk.style("key"), " SAVE ")
        ctx.hit(9, ay, 6, 1, "save", 1)
        nm = self.input_buf if self.input_mode else "(enter name)"
        st = sk.style("input_focus" if self.input_mode else "input")
        ctx.put(16, ay, st, f" {nm}")
        ctx.hit(16, ay, W - 20, 1, "savename", 1)

    # ---- chrome -----------------------------------------------------------
    def _draw_macros(self, ctx, W, H):
        sk = self.skin
        y = H - 4
        ctx.put(2, y, sk.style("heading"), "M1")
        ctx.put(6, y, sk.style("heading"), "M2")
        ctx.put(10, y, sk.style("heading"), "M3")
        ctx.put(14, y, sk.style("heading"), "M4")
        fw = max(6, (W - 26) // 4)
        for i in range(4):
            x = 18 + i * (fw + 2)
            self._draw_fader(ctx, x, y, fw, _Shim(-1.0, 1.0), self.macro[i], "macro", i)

    def _draw_footer(self, ctx, W, H):
        sk = self.skin
        y = H - 2
        msgs = "q quit · tab focus · ←→ + - adj · -/= oct · space demo · 1-4 screens · esc clear · qwe/asd/zxc = 40/70/100% · key depth = vel"
        if self.input_mode:
            hint = "enter commit · esc cancel"
        else:
            hint = "shift-drag (WT) selects text"
        ctx.put(2, y, sk.style("muted"), msgs[: W - len(hint) - 6])
        ctx.put(W - len(hint) - 3, y, sk.style("muted"), hint)
        if self.message and time.monotonic() - self.message_t < 4.0:
            ctx.put(2, H - 3, sk.style("status_warn"), f"  {self.message}"[: W - 6])
        elif not getattr(self.engine, "running", False) and self.engine.last_error:
            err = str(self.engine.last_error)[: W - 10]
            ctx.put(2, H - 3, sk.style("status_warn"), f"  {err}")

    # ---- mouse ------------------------------------------------------------
    def _hit(self, row, col):
        for hit in reversed(self._pending_hits):
            x, y, w, h, tag, payload = hit
            if x <= col < x + w and y <= row < y + h:
                return hit
        return None

    def _on_mouse(self, ev):
        row, col = ev.position.y, ev.position.x
        et = ev.event_type
        if et == MouseEventType.MOUSE_MOVE:
            hit = self._hit(row, col)
            self.hover = (hit[4], hit[5]) if hit else None
            if self.drag:
                self._drag_to(col)
            elif self.press:
                self._press_drag(row, col)
            self.app.invalidate()
            return
        hit = self._hit(row, col)
        if et == MouseEventType.SCROLL_UP or et == MouseEventType.SCROLL_DOWN:
            if hit:
                self._scroll(hit, et)
            return
        if et == MouseEventType.MOUSE_DOWN:
            if hit:
                self._click(hit, row, col, ev.button)
        elif et == MouseEventType.MOUSE_UP:
            self._end_press()
        self.app.invalidate()

    def _click(self, hit, row, col, button):
        x, y, w, h, tag, payload = hit
        if button == MouseButton.RIGHT:
            self._right_click(payload, tag)
            return
        if tag == "nav":
            self.screen = payload
            self.focus_id = None
        elif tag == "pad":
            self._pad_play(payload, True)
            if self.mode != "HOLD":
                self.press = {"type": "pad", "payload": payload}
        elif tag == "scale":
            self.scale = payload
        elif tag == "root":
            self.root = 45 + (payload - ((self.root - 45 + 60) % 12))
        elif tag == "mode":
            self.mode = payload
        elif tag == "oct":
            self.set_octave(payload)
        elif tag == "demo":
            self.demo.toggle()
            self.notify(f"demo {'on' if self.demo.running else 'off'}")
        elif tag == "pat":
            self.demo.cycle_pattern(payload)
            self.notify(f"loop {self.demo.pattern_name}")
        elif tag == "key":
            vel = self._key_velocity(row)
            self._key_play(payload, True, vel)
            self.press = {"type": "key", "payload": payload, "key": payload, "vel": vel}
        elif tag == "param":
            self.focus_id = ("param", payload)
            self.drag = {"tag": "param", "payload": payload, "x": x, "w": w, "y": y}
            self._drag_to(col)
        elif tag == "macro":
            self.focus_id = ("macro", payload)
            self.drag = {"tag": "macro", "payload": payload, "x": x, "w": w, "y": y}
            self._drag_to(col)
        elif tag == "morph":
            self.drag = {"tag": "morph", "payload": None, "x": x, "w": w, "y": y}
            self._drag_to(col)
        elif tag == "char":
            self._load_char(payload)
        elif tag == "copy":
            self._copy_side(payload)
        elif tag == "preset":
            self.sel_preset = payload
            self.focus_id = ("preset", payload)
        elif tag == "theme":
            self._preview_theme(payload)
        elif tag == "load":
            self._load_preset()
        elif tag == "save":
            self.input_buf = self.patch.name
            self.input_mode = True
        elif tag == "savename":
            self.input_mode = True
            self.input_buf = ""

    def _right_click(self, payload, tag):
        if tag == "param" and isinstance(payload, str):
            spec = BY_KEY[payload]
            self.set_param(payload, spec.default)
            self.notify(f"{spec.label} -> default")
        elif tag == "macro" and isinstance(payload, int):
            self.macro[payload] = 0.0
            self._push_live()
        elif tag == "morph":
            self.morph = 0.5
            self._push_live()

    def _drag_to(self, col):
        d = self.drag
        if not d:
            return
        t = (col - (d["x"] + 1)) / max(1, d["w"] - 2)
        if d["tag"] == "macro":
            self.macro[d["payload"]] = clamp(t * 2.0 - 1.0, -1.0, 1.0)
            self._push_live()
        elif d["tag"] == "morph":
            self.morph = clamp(t, 0.0, 1.0)
            self._push_live()
        elif d["tag"] == "param":
            spec = BY_KEY[d["payload"]]
            self.set_param(d["payload"], from01(spec, t))

    def _key_velocity(self, row: int) -> float:
        """Velocity from click depth: the bottom ``_VEL_ROWS`` rows are 100%."""
        _x, _kw, _n0, _nk, body_top, rows = self._keygeom
        r = row - body_top
        if r < 0 or r >= rows:
            return 0.85
        safe = min(_VEL_ROWS, rows)
        if r >= rows - safe:
            return 1.0
        t = (r + 1) / (rows - safe)
        return round(0.15 + 0.85 * t, 3)

    def _press_drag(self, row, col):
        p = self.press
        if not p or p["type"] != "key":
            return
        x0, key_w, note0, nkeys, body_top, rows = self._keygeom
        i = (col - x0) // key_w
        if 0 <= i < nkeys:
            midi = note0 + i
            if p.get("key") != midi:
                self._key_play(p["key"], False, p.get("vel", 0.85))
                vel = self._key_velocity(row)
                self._key_play(midi, True, vel)
                p["key"] = midi
                p["vel"] = vel

    def _end_press(self):
        p = self.press
        if not p:
            self.drag = None
            return
        if p["type"] == "key":
            self._key_play(p.get("key", p["payload"]), False)
            self.key_lit.discard(p.get("key", p["payload"]))
        elif p["type"] == "pad":
            self._pad_play(p["payload"], False)
        self.press = None
        self.drag = None

    def _pad_play(self, idx, on: bool):
        r, c = divmod(idx, 4)
        deg = DEG_LABELS[self.scale][c]
        spell = CHORD_SETS[self.scale][deg]
        root = self.root + [-12, 0, 12, 24][r]
        notes = [root + s for s in spell]
        if not on:
            if self.mode == "ARP" and idx in self.arp_stop:
                self.arp_stop[idx].set()
            self._release_notes(notes)
            self.active_pads.discard(idx)
            return
        if self.mode == "HOLD":
            if idx in self.active_pads:
                self._release_notes(notes)
                self.active_pads.discard(idx)
                return
            self.active_pads.add(idx)
            self._play_notes(notes)
        elif self.mode == "ARP":
            self.active_pads.add(idx)
            self._start_arp(idx, notes)
        else:
            self.active_pads.add(idx)
            self._play_notes(notes)

    def _play_notes(self, notes):
        for n in notes:
            self.engine.push("note_on", n, 0.7)

    def _release_notes(self, notes):
        for n in notes:
            self.engine.push("note_off", n)

    def _start_arp(self, idx, notes):
        stop = threading.Event()
        self.arp_stop[idx] = stop
        threading.Thread(target=self._arp_loop, args=(notes, stop), daemon=True).start()

    def _arp_loop(self, notes, stop):
        step = 60.0 / 96.0 / 2.0
        i = 0
        while not stop.is_set():
            n = notes[i % len(notes)]
            self.engine.push("note_on", n, 0.5)
            self.engine.push("note_off", n)
            i += 1
            stop.wait(step)

    def _key_play(self, midi, on: bool, vel: float = 0.85):
        if on:
            self.engine.push("note_on", midi, vel)
            self.key_lit.add(midi)
        else:
            self.engine.push("note_off", midi)
            self.key_lit.discard(midi)

    def _kbd_play(self, key: str):
        i = _KBD_INDEX.get(key)
        if i is None:
            return
        note = 48 + i
        vel = _KBD_VEL[i // 12]
        if note in self.kbd_events:
            return  # key held: ignore auto-repeat
        self.engine.push("note_on", note, vel)
        ev = threading.Event()
        self.kbd_events[note] = ev
        threading.Thread(target=self._kbd_off, args=(note, ev), daemon=True).start()

    def _kbd_off(self, note: int, ev: threading.Event):
        if not ev.wait(_KBD_HOLD) and self.kbd_events.get(note) is ev:
            self.engine.push("note_off", note)
            self.kbd_events.pop(note, None)

    # ---- patch / library actions -----------------------------------------
    def _copy_side(self, which):
        if which > 0:
            self.patch.b = dict(self.patch.a)
        else:
            self.patch.a = dict(self.patch.b)
        self._push_live()
        self.notify("A/B copied")

    def _load_char(self, name):
        from .param import load_preset
        from pathlib import Path
        base = Path(__file__).resolve().parent.parent / "presets"
        fname = {"PAD": "hollow-pad", "STR": "veil-string", "AIR": "upper-air",
                 "AMB": "gale-ambience"}[name]
        p = load_preset(base / f"{fname}.json")
        self.patch.name = p.name
        self.patch.char = p.char
        self.patch.a = p.a
        self.patch.b = p.b
        self.patch.macros = p.macros
        self.morph = p.morph
        self._push_live()
        self.notify(f"char {name}: {p.name}")

    def _load_preset(self):
        presets = list_presets()
        if not presets or self.sel_preset >= len(presets):
            return
        from .param import load_preset
        p = load_preset(presets[self.sel_preset])
        self.patch.name = p.name
        self.patch.char = p.char
        self.patch.a = p.a
        self.patch.b = p.b
        self.patch.macros = p.macros
        self.morph = p.morph
        self._push_live()
        self.notify(f"loaded {p.name}")

    def _save(self):
        name = self.input_buf.strip() or self.patch.name
        self.patch.name = name
        from .param import PRESETS_DIR
        PRESETS_DIR.mkdir(parents=True, exist_ok=True)
        save_preset(self.patch, PRESETS_DIR / f"{name.replace(' ', '-').lower()}.json")
        self.notify(f"saved {name}")

    def _preview_theme(self, idx):
        themes = list_themes()
        if idx >= len(themes):
            return
        from .themes import load_theme
        self.theme_preview = load_theme(themes[idx])
        self.skin = self.theme_preview
        self.sel_theme = idx
        self.notify(f"skin {self.skin.name} previewing")

    def _commit_theme(self):
        if self.theme_preview is not None:
            self.theme_preview = None
            self.notify(f"skin committed: {self.skin.name}")

    def _rollback_theme(self):
        if self.theme_preview is not None:
            self.theme_preview = None
            from .themes import load_any_theme
            try:
                self.skin = load_any_theme(self.args.theme)
            except Exception:
                pass

    def _scroll(self, hit, evtype):
        tag, payload = hit[4], hit[5]
        d = -1 if evtype == MouseEventType.SCROLL_UP else 1
        if tag == "param":
            self.change_param(payload, 0.03 * d if BY_KEY[payload].log else
                              (BY_KEY[payload].hi - BY_KEY[payload].lo) * 0.02 * d)
        elif tag == "macro":
            self.macro[payload] = clamp(self.macro[payload] + d * 0.1, -1, 1)
            self._push_live()
        elif tag == "preset":
            self.sel_preset = clamp(self.sel_preset + d, 0, max(0, len(list_presets()) - 1))
            self.focus_id = ("preset", self.sel_preset)
        elif tag == "theme":
            self._preview_theme(clamp(self.sel_theme + d, 0, max(0, len(list_themes()) - 1)))

    # ---- keyboard ----------------------------------------------------------
    def _build_keys(self):
        kb = KeyBindings()

        @kb.add("c-q")
        def _quit(event):
            self._running = False
            event.app.exit()

        @kb.add("<any>")
        def _any(event):
            key = event.key_sequence[0].key
            if not isinstance(key, str):
                key = key.name.lower()
            if self.input_mode:
                if isinstance(key, str) and len(key) == 1 and key.isprintable():
                    self.input_buf += key
                elif key in ("backspace", "c-h"):
                    self.input_buf = self.input_buf[:-1]
                elif key == "enter":
                    self._save()
                    self.input_mode = False
                elif key == "escape":
                    self.input_mode = False
                event.app.invalidate()
                return
            if key == "tab":
                self._focus_next(1)
            elif key in ("s-tab", "backtab"):
                self._focus_next(-1)
            elif key == "space":
                self.demo.toggle()
                self.notify(f"demo {'on' if self.demo.running else 'off'}")
            elif key in ("-", "="):
                self.set_octave(-1 if key == "-" else 1)
            elif key in _KBD_INDEX:
                self._kbd_play(key)
            elif key in ("1", "2", "3", "4"):
                self.screen = SCREENS[int(key) - 1]
                self.focus_id = None
            elif key == "r":
                self._reset_focus()
            elif key == "left":
                self._adjust(-1)
            elif key == "right":
                self._adjust(1)
            elif key == "up":
                self._adjust(1)
            elif key == "down":
                self._adjust(-1)
            elif key == "enter":
                self._activate_focus()
            elif key == "escape":
                if self.theme_preview:
                    self._rollback_theme()
                elif self.focus_id:
                    self.focus_id = None
            event.app.invalidate()

        for i, ch in enumerate(("!", "@", "#", "$")):
            @kb.add(ch)
            def _macro_focus(event, _i=i):
                self.focus_id = ("macro", _i)
                event.app.invalidate()

        return kb

    def _focus_items(self):
        items: list[tuple] = []
        if self.screen == "PATCH":
            for p in PARAMS:
                if group_of(p.key) in ("voice", "filter", "env", "lfo", "pan"):
                    items.append(("param", p.key))
            items.append(("morph", None))
        elif self.screen == "MIX":
            for p in PARAMS:
                if group_of(p.key) in ("fx", "mix"):
                    items.append(("param", p.key))
        elif self.screen == "LIBRARY":
            items.append(("preset", self.sel_preset))
            items.append(("theme", self.sel_theme))
        for i in range(4):
            if self.patch.macros:
                items.append(("macro", i))
        return items

    def _focus_next(self, d):
        items = self._focus_items()
        if not items:
            return
        i = items.index(self.focus_id) if self.focus_id in items else -1
        self.focus_id = items[(i + d) % len(items)]

    def _adjust(self, delta):
        f = self.focus_id
        if not f:
            return
        if f[0] == "param":
            spec = BY_KEY[f[1]]
            if spec.discrete:
                t = to01(spec, self.patch.a[f[1]] if self.morph <= 0.5 else self.patch.b[f[1]])
                nt = t + delta / max(1, (spec.hi - spec.lo))
                v = round(from01(spec, nt))
                v = max(spec.lo, min(spec.hi, float(v)))
                self.set_param(f[1], v)
            else:
                self.change_param(f[1], delta * 0.02)
        elif f[0] == "macro":
            self.macro[f[1]] = clamp(self.macro[f[1]] + delta * 0.1, -1, 1)
            self._push_live()
        elif f[0] == "morph":
            self.morph = clamp(self.morph + delta * 0.05, 0, 1)
            self._push_live()
        elif f[0] == "preset":
            self.sel_preset = clamp(self.sel_preset + delta, 0, max(0, len(list_presets()) - 1))
        elif f[0] == "theme":
            self._preview_theme(clamp(self.sel_theme + delta, 0, max(0, len(list_themes()) - 1)))

    def _activate_focus(self):
        if self.focus_id and self.focus_id[0] == "preset":
            self._load_preset()
        elif self.focus_id and self.focus_id[0] == "theme":
            self._commit_theme()

    def _reset_focus(self):
        if self.focus_id and self.focus_id[0] == "param":
            spec = BY_KEY[self.focus_id[1]]
            self.set_param(self.focus_id[1], spec.default)
            self.notify(f"{spec.label} reset")

    # ---- loop --------------------------------------------------------------
    def _refresh_loop(self):
        first_error: tuple | None = None
        while self._running:
            time.sleep(1.0 / 14.0)
            try:
                self._render()
                self._frame_error = None
                self.app.invalidate()
            except Exception:
                if first_error is None:
                    first_error = sys.exc_info()
                    import traceback
                    traceback.print_exception(*first_error, file=sys.stderr)
                    self._frame_error = f"{first_error[0].__name__}: {first_error[1]}"
                    try:
                        self._render_frame_error()
                        self.app.invalidate()
                    except Exception:
                        pass

    def run(self):
        try:
            self.app.run()
        finally:
            self._running = False
            self.engine.stop()
            self.demo.stop()
            if self.midi:
                self.midi.close()
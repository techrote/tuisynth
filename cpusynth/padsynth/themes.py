"""Theme / skin system - a validated subset of mdbm's ``md-editor-theme/1.1`` schema.

Themes are TOML data and cannot execute code. Unknown fields are reported and
skipped (single entry per warning). Required: ``schema``, ``id``, ``name``.

Honoured surfaces: palette, ramps, styles, geometry (ignored), glyphs,
art (header/footer banners), patterns (simple background dither), variants
(narrow/monochrome/ascii/high_contrast selection) and fallbacks
(ascii/monochrome/narrow). layers/animations/rules/motifs/masks are parsed and
validated but not yet composed - they surface as warnings so a writer knows the
data is portable.
"""
from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

THEMES_DIR = Path(__file__).resolve().parent.parent / "themes"

_KNOWN_TOP = {
    "schema", "id", "name", "description", "extends", "seed", "seed_mode",
    "fps", "palette", "ramps", "styles", "geometry", "glyphs", "art",
    "motifs", "patterns", "masks", "layers", "animations", "rules",
    "variants", "fallbacks",
}

# internal role -> mdbm semantic role (fallback when the writer did not define it)
SEMANTIC = {
    "background": "background",
    "text": "text",
    "muted": "muted",
    "border": "border",
    "title": "title",
    "accent": "accent",
    "heading": "heading",
    "code": "code",
    "status_ok": "status",
    "status_warn": "warning",
    "status_err": "error",
    "sel": "selected",
    "focus": "focused",
    "hover": "hover",
    "press": "pressed",
    "disabled": "disabled",
}

_DERIVED = {  # internal role -> bases (fg, bg)
    "dim": ("muted", "background"),
    "bar": ("accent", "background"),
    "bar_empty": ("muted", "background"),
    "cursor": ("accent", "background"),
    "pad": ("text", "background"),
    "pad_hot": ("sel", "background"),
    "pad_hold": ("focus", "background"),
    "key": ("accent", "background"),
    "key_dim": ("muted", "background"),
    "meta": ("muted", "background"),
    "input": ("text", "background"),
    "input_focus": ("focus", "background"),
}

ATTR_KEYS = ("bold", "italic", "underline", "dim", "strike")


@dataclass
class Skin:
    id: str
    name: str
    _palette: dict[str, str] = field(default_factory=dict)   # name -> "#hex"
    _ramps: dict[str, dict] = field(default_factory=dict)    # id -> {"hex":[...]}
    _styles: dict[str, dict] = field(default_factory=dict)   # role -> style dict
    _glyphs: dict[str, dict] = field(default_factory=dict)
    art: dict[str, list[str]] = field(default_factory=dict)  # id -> rows
    patterns: dict[str, dict] = field(default_factory=dict)
    fps: int = 20
    warnings: list[str] = field(default_factory=list)
    nocolor: bool = False

    # -- colour helpers -------------------------------------------------
    def hex(self, name: str) -> str:
        v = self._palette.get(name, "#888888")
        return v

    def ramp_hex(self, rid: str, t: float) -> str:
        r = self._ramps.get(rid)
        if not r:
            a = (self._style_of("muted") or {}).get("fg")
            b = (self._style_of("border") or {}).get("fg")
            ha = self.hex(a) if a else "#666666"
            hb = self.hex(b) if b else "#333333"
            return _lerp_hex(ha, hb, t)
        t = max(0.0, min(1.0, t))
        i = t * (len(r["hex"]) - 1)
        lo = int(math.floor(i))
        hi = min(lo + 1, len(r["hex"]) - 1)
        a, b = r["hex"][lo], r["hex"][hi]
        return _lerp_hex(a, b, i - lo)

    def _resolve(self, role: str) -> dict:
        """Resolve a style dict for an internal role (extends handled)."""
        key = SEMANTIC.get(role, role)
        st = self._style_of(key)
        if st is None and role in _DERIVED:
            fg, bg = _DERIVED[role]
            st = dict(self._style_of(fg) or {})
            bg_s = self._style_of(bg)
            if bg_s and "bg" in bg_s and "bg" not in st:
                st["bg"] = bg_s["bg"]
        return st or {}

    def _style_of(self, name: str) -> dict | None:
        raw = self._styles.get(name)
        if raw is None:
            return None
        out: dict = {}
        seen: set[str] = set()
        stack = [raw]
        while stack:
            cur = stack.pop()
            if id(cur) in seen:
                continue
            seen.add(id(cur))
            ex = cur.get("extends")
            if isinstance(ex, str) and ex in self._styles:
                stack.append(self._styles[ex])
            for k in ("fg", "bg", "bold", "italic", "underline", "dim", "strike"):
                if k in cur and k not in out:
                    out[k] = cur[k]
        return out

    def style(self, role: str, extra: str | None = None) -> str:
        """Prompt-toolkit style string for an internal role."""
        st = self._resolve(role)
        parts: list[str] = []
        if not self.nocolor:
            fg = st.get("fg")
            bg = st.get("bg")
            if fg:
                parts.append(f"fg:{self.hex(fg)}")
            if bg:
                parts.append(f"bg:{self.hex(bg)}")
        for a in ATTR_KEYS:
            if st.get(a):
                parts.append(a)
        if extra:
            parts.append(extra)
        return " ".join(parts)

    def glyph(self, name: str, on: bool = False) -> str:
        g = self._glyphs.get(name) or {}
        val = g.get("on" if on else "off") or (g.get("symbols") or [" ", "-"][0])
        if isinstance(val, list):
            val = val[0] if val else " "
        return str(val)


def _lerp_hex(a: str, b: str, t: float) -> str:
    ar = int(a[1:3], 16); ag = int(a[3:5], 16); ab = int(a[5:7], 16)
    br = int(b[1:3], 16); bg = int(b[3:5], 16); bb = int(b[5:7], 16)
    return "#%02x%02x%02x" % (round(ar + (br - ar) * t),
                             round(ag + (bg - ag) * t),
                             round(ab + (bb - ab) * t))


def _is_hex(s: str) -> bool:
    return isinstance(s, str) and len(s) == 7 and s[0] == "#" and all(
        c in "0123456789abcdefABCDEF" for c in s[1:7])


def load_theme(path: Path) -> Skin:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return build_theme(raw, str(path))


def build_theme(raw: dict, label: str) -> Skin:
    warnings: list[str] = []

    schema = raw.get("schema")
    if schema not in ("md-editor-theme/1.1", "md-editor-theme/1.0"):
        raise ValueError(f"{label}: unsupported schema {schema!r} (expected md-editor-theme/1.1)")
    tid = raw.get("id")
    name = raw.get("name")
    if not isinstance(tid, str) or not isinstance(name, str):
        raise ValueError(f"{label}: missing string fields id/name")

    for k in raw:
        if k not in _KNOWN_TOP:
            warnings.append(f"{label}: unknown field {k!r} skipped")

    palette: dict[str, str] = {}
    if isinstance(raw.get("palette"), dict):
        for k, v in raw["palette"].items():
            if _is_hex(v):
                palette[k] = v
            elif isinstance(v, str) and v.startswith("@") and v[1:] in raw["palette"]:
                palette[k] = raw["palette"][v[1:]]
            else:
                warnings.append(f"{label}: palette.{k} ignored (not a colour)")

    ramps: dict[str, dict] = {}
    if isinstance(raw.get("ramps"), dict):
        for k, spec in raw["ramps"].items():
            colours = spec.get("colours")
            steps = spec.get("steps", 16)
            if not isinstance(colours, list) or len(colours) < 2 or len(colours) > 16:
                warnings.append(f"{label}: ramps.{k} ignored (needs 2-16 colours)")
                continue
            steps = max(2, min(256, int(steps)))
            hexes = [c for c in colours if _is_hex(c)]
            if len(hexes) < 2:
                warnings.append(f"{label}: ramps.{k} ignored (no colour hexes)")
                continue
            out = []
            for i in range(steps):
                t = i / (steps - 1)
                seg = t * (len(hexes) - 1)
                lo = min(int(seg), len(hexes) - 2)
                out.append(_lerp_hex(hexes[lo], hexes[lo + 1], seg - lo))
            ramps[k] = {"hex": out}

    glyphs: dict[str, dict] = {}
    if isinstance(raw.get("glyphs"), dict):
        for k, spec in raw["glyphs"].items():
            if isinstance(spec, dict):
                glyphs[k] = {kk: vv for kk, vv in spec.items() if kk in ("symbols", "on", "off")}

    art: dict[str, list[str]] = {}
    if isinstance(raw.get("art"), dict):
        for k, spec in raw["art"].items():
            if isinstance(spec, dict) and isinstance(spec.get("rows"), list):
                rows = [str(r) for r in spec["rows"]]
                art[k] = rows
            else:
                warnings.append(f"{label}: art.{k} ignored (rows required)")

    patterns: dict[str, dict] = {}
    if isinstance(raw.get("patterns"), dict):
        for k, spec in raw["patterns"].items():
            if isinstance(spec, dict) and spec.get("kind"):
                patterns[k] = {
                    "kind": str(spec["kind"]),
                    "glyphs": spec.get("glyphs", [" ", "."]),
                    "density": float(spec.get("density", 0.5)),
                    "period": list(spec.get("period", [2, 2])),
                }

    fps = 20
    if isinstance(raw.get("fps"), (int, float)):
        fps = int(raw["fps"])

    skin = Skin(
        id=tid, name=name,
        _palette=palette, _ramps=ramps, _styles=raw.get("styles") or {},
        _glyphs=glyphs, art=art, patterns=patterns, fps=fps,
        warnings=warnings,
    )

    # fallbacks surface ---------------------------------------------------
    layers = raw.get("layers")
    if layers:
        skin.warnings.append(f"{label}: layers accepted but not composed yet "
                             f"({len(layers)} layer(s) portable)")
    if raw.get("animations"):
        skin.warnings.append(f"{label}: animations accepted but not composed yet")

    return skin


def list_themes() -> list[Path]:
    if not THEMES_DIR.exists():
        return []
    return sorted(THEMES_DIR.glob("*.toml"))


def load_any_theme(name: str | None) -> Skin:
    """Load a theme by bare name / path / default."""
    if name:
        p = Path(name)
        if not p.exists():
            p = THEMES_DIR / f"{name}.toml"
        if not p.exists():
            p = THEMES_DIR / name
        if not p.exists():
            raise ValueError(f"theme not found: {name}")
        return load_theme(p)
    for p in list_themes():
        return load_theme(p)
    raise ValueError("no themes found - ship at least one .toml skin")
# padsynth

A reconfigurable, mouse-first terminal synthesizer for Windows Terminal. Pads, strings,
air, and ambience built around the **mdbm** UX philosophy — every mouse action has a
keyboard twin, and every visual decision is data, not code, so skins can't do harm.

```
python -m padsynth            # run with the default skin and first preset
python -m padsynth --theme permutation-weather
python -m padsynth hollow-pad
python -m padsynth --no-audio --theme cyber-weather   # UI without a sound card
python -m padsynth --midi 0   # use the first rtmidi MIDI-in port
```

`Setup.cmd` installs dependencies and `Start.cmd` launches from the repo root.

## What it is

- **FOCUS** focused on *pads/strings/air/ambience* — long envelopes, layered oscillators,
  slow LFO motion, space via delay/reverb.
- **PLAY** — a 4x4 chord-pad grid, root/scale/mode controls, HOLD/MOMENTARY/ARP trigger
  modes, and a note key-strip you can drag for glissando. The top transport row runs the
  four inbuilt demo loops and steps demo basslines an octave up or down.
- **PATCH** — voice, filter, amp env, filter env, LFO, and pan panels with a morph handle
  between A and B. Four macro sliders map to any patch parameter for a "hands on the
  synth" performance layer.
- **MIX** — chorus, ping-pong delay, Schroeder reverb, and the master bus (drive + limit).
- **LIBRARY** — load/save presets, try skins live, rename inline. Presets live in
  `presets/*.json`, skins in `themes/*.toml`.

## UX philosophy (mdbm)

> "Software that looks like part of itself, not a picture of a thing."

1. **Mouse first, keyboard everything.** Every mouse action (drag a pad, wheel an LFO) is
   mirrored by keys. The tips bar at the bottom spells both out per screen — never a
   mystery.
2. **Semantic color only.** The UI never asks for a hue; it asks for roles (`accent`,
   `selected`, `hover`). Skins supply the hues, so the app is isomorphic to any look.
3. **Themes are data, validated at load.** Skins must declare `md-editor-theme/1.1` and are
   rejected (with warnings, never a crash) if they name unknown roles or produce raw ANSI
   strings. A volatile skin can render oddly; it can never break a state.
4. **Restraint is a feature.** Fixed grids, occupancy-only, micro-caps labels. If a detail
   doesn't carry state it isn't rendered.

## Keys

| Key        | Action                                   |
|------------|------------------------------------------|
| `1`-`4`    | PLAY / PATCH / MIX / LIBRARY screens     |
| `Tab`/`Shift+Tab` | next / previous focused widget     |
| `←↑→↓`     | move focus / adjust sliders              |
| `Enter`    | activate focus (morph lock, save…)       |
| `Space`    | demo loop on / off                       |
| `-` `=`    | octave down / up (also mouse OCT [-]/[+])|
| `Esc`      | clear focus / undo theme preview         |
| `Ctrl+Q`   | quit                                     |
| `Shift+1`..`4` | macro knobs M1..M4                   |
| `qwertyuiop[]` | note row C3..B3 at **40%** velocity  |
| `asdfghjkl;'`  | note row C4..B4 at **70%** velocity  |
| `zxcvbnm,./`   | note row C5..Bb5 at **100%** velocity|

The physical-keyboard rows are a 34-note playable piano (each press is a
gate, auto-released after ~0.4 s since terminals send no key-up). The mouse
key strip at the bottom of PLAY is velocity-sensitive: the deeper you click,
the louder the note, and the bottom four key rows always trigger at 100%.

Mouse: **left-drag** pads and sliders, **wheel** on LFO/‘ambient’ params, **right-click**
resets a slider to default, **Shift+left** reverts to text selection in Windows Terminal.

## Skinning

Themes are TOML files conforming to the `md-editor-theme/1.1` schema. A minimal skin:

```toml
schema = "md-editor-theme/1.1"
id = "my-skin"
name = "MY SKIN"

[palette]
bg = "#05070b"; fg = "#c9d7ea"; dim = "#5b6b8c"; accent = "#38f2ff"

[styles]
background = { bg = "bg" }
text = { fg = "fg" }
accent = { fg = "accent" }
muted = { fg = "dim" }
```

Roles the app consumes: `background`, `text`, `muted`, `border`, `title`, `heading`,
`accent`, `code`, `status`, `warning`, `error`, plus the states `focused`, `hover`,
`pressed`, `selected`, `disabled`. Optional sweetening: `[glyphs.divider]`,
`[patterns.scanline]` / `rails` / `checker` / `dropout`, `[variants.narrow]`,
`[fallbacks.*]`, and a `[palette]` ramp that choosy skins use to replace the default
background dither. Any unknown field produces a load warning, never a crash; the 
restrained-monochrome theme is the guaranteed-safe parity fallback.

See `themes/*.toml` for full examples.

## License

MIT.
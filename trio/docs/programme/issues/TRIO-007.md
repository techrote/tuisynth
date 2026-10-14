# [TRIO-007] Kit: TUI canvas, mouse, widgets and headless driver

Work in `techrote/tuisynth` on **TRIO-007** and complete it end-to-end: implementation,
tests, pull request, CI fixes and merge after every automated check is green.

## Depends on

- TRIO-002 (#3) and TRIO-006 (#7) must be closed.

## Read first

1. `trio/AGENTS.md`
2. This issue and all comments
3. `trio/docs/rag/04-TUI-UX-CONTRACT.md` sections "Philosophy", "Rendering model", "Mouse model",
   "Widget set", "Headless test driver"
4. `trio/docs/rag/05-SKINS-CONTRACT.md` sections "Required roles", "Colour depth"
5. `trio/docs/rag/11-LESSONS-FROM-RECOVERY.md` row PAD-001
6. Reference only: `cpusynth/padsynth/ui.py` (`_Ctx`, `_CanvasControl`, `_on_mouse`) and
   prompt_toolkit's `create_pipe_input`/`DummyOutput` API

## Objective

The drawing and interaction layer: a cell canvas with an exact hit map, mouse capture/drag,
a complete widget set with keyboard twins, and a headless driver that injects **real SGR mouse
bytes** so mouse behaviour is tested the way terminals actually deliver it.

## Files (under `trio/kit/src/trio_kit/tui/`)

- `canvas.py`: `Canvas(width, height, skin)` with the primitives in TRIO-UX "Rendering model";
  cells store `(glyph, role, state)`; `fragments() -> list[tuple[str, str]]` for prompt_toolkit;
  `text() -> str` (plain text for snapshots); clipping is silent; `wcwidth` check rejects
  double-width glyphs by substituting `?`.
- `hitmap.py`: `HitMap.add(x, y, w, h, target, payload)`, `find(x, y) -> Hit | None` (last added
  wins), cleared each frame.
- `mouse.py`: `MouseRouter` turning prompt_toolkit `MouseEvent`s into widget calls with capture:
  `down(x, y, button)`, `move(x, y)` (drag when captured, hover otherwise), `up(x, y)`,
  `wheel(x, y, delta)`; right button = reset/alt action. Mouse coordinates are converted from
  prompt_toolkit's 0-based `position.x/.y`; document the convention in the module docstring.
- `focus.py`: `FocusRing` (Tab/Shift+Tab order, focused widget gets keys).
- `widgets/`: `base.py` (`Widget` with `draw(canvas, x, y, w, h)`, `on_key`, `on_mouse_*`,
  `focusable`), `fader.py`, `knob.py`, `toggle.py`, `choice.py`, `xypad.py`, `meter.py`,
  `button.py`, `textfield.py`, `listbox.py`, `tabs.py`. Param-bound widgets take
  `(registry, key, get_value: Callable[[], float], on_change: Callable[[str, float], None])`
  and implement the keyboard and mouse behaviour in TRIO-UX "Widget set" and "Mouse model".
- `app.py`: `CanvasApp(root: Widget, skin, size_hint=None)` wrapping a prompt_toolkit
  `Application(full_screen=True, mouse_support=True)` with one `FormattedTextControl` whose
  mouse handler feeds `MouseRouter`; key bindings forward to the focused widget; invalidation
  throttled to <= 30 fps; render exceptions draw an error panel (role `error`) instead of
  propagating.
- `testing.py`: `HeadlessApp(app, cols, rows)` exactly as TRIO-UX "Headless test driver";
  `sgr(button, x, y, release=False) -> str` builds `\x1b[<b;x;yM` / `m` with 1-based coordinates.
- `demo.py`: `python -m trio_kit.tui.demo` showing every widget bound to a demo registry
  (manual check aid; also used by tests).

## Tests (names are binding; `trio/kit/tests/tui/`)

- `test_canvas.py`: primitives, clipping, `text()` output, double-width substitution.
- `test_hitmap.py`: every cell of a set of rectangles maps back to its target; overlap order.
- `test_sgr_mouse.py`: through `HeadlessApp`, real SGR click on each corner cell of a 3x2
  `Button` grid activates exactly that button (proves 1-based to 0-based mapping; the PAD-001
  failure mode); drag capture continues outside the widget; release outside still ends the
  drag; wheel steps a fader; right-click resets to default.
- `test_widgets_keyboard.py`: for each param-bound widget, arrows/PageUp/PageDown/Home/End/Delete
  produce the documented values via `on_change`; Tab order.
- `test_widgets_mouse.py`: fader drag maps positions to values monotonically (linear and log
  params); knob vertical drag; XY pad emits both axes; listbox click selects.
- `test_error_panel.py`: a widget whose `draw` raises results in an error panel and the app
  keeps processing keys (`Ctrl+Q` still exits).
- `test_snapshots.py`: golden text of the widget demo at 100x30 with skin `kit-demo` and `mono`
  (`--update-snapshots` support via a pytest option registered in `conftest.py`).

## Acceptance criteria

- Mouse tests use real SGR byte sequences through prompt_toolkit input, not direct method calls.
- Widgets never import `trio_kit.engine`.
- `python trio/tools/check.py --package all` green; both CI workflows green.

## Out of scope

On-screen piano, app shell overlays, CLI (TRIO-008).

## Delivery

Follow `trio/AGENTS.md` sections 2-7. Branch `trio-007-tui`.

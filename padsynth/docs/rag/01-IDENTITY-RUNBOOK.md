---
synth_id: padsynth
document_id: PAD-RUN
source_archive_sha256: 419d4f504cbaa01eaeb46e3c58050466a6cca9cc015a365ba1a10bef8f139b67
---
# PadSynth: identity and runbook

## Identity

The archive label `padsynth` is the collection identity; the original package/distribution/CLI is
`padsynth`, version `0.1.0`, requiring Python **3.11 or newer** in [pyproject.toml](../../pyproject.toml).
This is a Python source workspace, not a packaged Windows executable. The included `.venv` contained
machine-specific dependencies, not a separate synth implementation. It is excluded and must be recreated.
Exact per-model OpenCode authorship is not present in the retained source and is not asserted.

## Run from this directory, in a separate virtual environment

Never install all three projects into one environment: their distribution/module/entry-point names collide.
The supported recovery launch route is **source-directory execution**, not `pip install .` or a wheel.
The packaging review records unresolved distribution defects.

On Windows, open this directory in Windows Terminal and run `1Setup.cmd`, then `0Start.cmd`.
`0Start.cmd` can also create the environment on first launch. On any host, the explicit equivalent is:

```sh
python -m venv .venv
# Activate .venv using the shell's normal activation command.
python -m pip install -r requirements.txt
python padsynth.py --diagnostics --no-restore
python padsynth.py --snapshot 100x28 --no-restore
python padsynth.py --render audition.wav --seconds 2.5 --notes C3,E3,G3 --seed 7
python padsynth.py
```

Use `--list-patches`, `--list-themes` and `--validate-theme themes/teal-core.theme` for inspection.
`--demo` renders `demo-medley.wav` into the current working directory; it does not play it.
`--demo-play` additionally requests playback. Preserve the supplied medley before intentionally replacing it.
For guaranteed device-free CLI inspection/rendering, copy the config and set `[audio] device = "null"`,
then pass `--config path/to/that.conf`; the default `auto` route may probe installed audio backends.

The TUI requires prompt-toolkit; offline render/diagnostic/snapshot code uses the standard library.
Actual sound uses optional `sounddevice` plus NumPy, or Windows `winsound`; otherwise the explicit
`null` backend renders silently. The source requirements file installs only the TUI dependency.
There is no external MIDI-input implementation in this standalone file.

## Review reproduction

From the collection root, install `requirements-review.txt` in a dedicated review environment and run
`python tools/validate.py`. It verifies all original hashes and starts a fresh test process per synth.
Alternatively, from this directory run `python -m pytest -q -rx tests` after installing those review
requirements. Local evidence uses Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0, prompt-toolkit 3.0.53,
wcwidth 0.8.3 and pytest 9.0.2. Pure-Python prompt-toolkit/wcwidth were read from the uploaded environment
for testing because the execution container could not reach package indexes. Native Windows binaries
were never executed in Linux. Hosted CI is separately reported by GitHub, not inferred from these logs.

## Troubleshooting and limits

Start with device-free tests before speaker output. First physical listening should use low system gain;
passing finite-buffer tests is not a loudness or hearing-safety certification. No actual audio device,
MIDI interface or Windows Terminal interaction was qualified in the local review. Recreate rather than
copy a virtual environment; launch from the matching source directory when presets/themes cannot be found.

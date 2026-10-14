---
synth_id: niceglitchsynth
document_id: NG-RUN
source_archive_sha256: ae570a12568ff0158682d3e844de143007fb877306dcc69ea0752eebdb8272f4
---
# Nice Glitch Synth: identity and runbook

## Identity

The archive label `niceglitchsynth` is the collection identity; the original package/distribution/CLI is
`padsynth`, version `0.1.0`, requiring Python **3.11 or newer** in [pyproject.toml](../../pyproject.toml).
This is a Python source workspace, not a packaged Windows executable. The included `.venv` contained
machine-specific dependencies, not a separate synth implementation. It is excluded and must be recreated.
Exact per-model OpenCode authorship is not present in the retained source and is not asserted.

## Run from this directory, in a separate virtual environment

Never install all three projects into one environment: their distribution/module/entry-point names collide.
The supported recovery launch route is **source-directory execution**, not `pip install .` or a wheel.
The packaging review records unresolved distribution defects.

On Windows, open this directory in Windows Terminal and run `Setup.cmd`, then `Start.cmd`.
The launcher changes to its own directory and invokes the local environment. Explicit equivalent:

```sh
python -m venv .venv
# Activate .venv using the shell's normal activation command.
python -m pip install -r requirements.txt
python -m padsynth --no-audio --theme cyber-weather
python -m padsynth hollow-pad
python -m padsynth --midi 0
```

`--no-audio` avoids creating an audio device. The offline engine exposes `render(n)` for tests but
this entry point has no `--render` or `--snapshot` CLI option; those belong to the standalone sibling.
The source dependency list includes NumPy, prompt-toolkit, sounddevice and python-rtmidi.
CPU Synth alone optionally uses SciPy when installed; Nice Glitch does not use that optional fast path.
MIDI port selection is optional. A failed audio start falls back to an OfflineEngine with an error message.

`engine.start()` may create a real output stream. Do not call it in device-free test code.
Construct `OfflineEngine()` or `make_engine(True)` and provide `Patch.live()` parameters instead.
Use block-multiple render sizes until MOD-003 is repaired.

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

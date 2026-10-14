"""The original adaptive/glitch policy is preserved, not repaired away."""
from types import SimpleNamespace
import numpy as np
from padsynth.engine.core import AudioEngine
from padsynth.engine.synth import BLOCK, UNI_MAX
from padsynth.param import default_patch


def test_pressure_escalates_and_quiet_recovers():
    e = AudioEngine()
    underflow = SimpleNamespace(output_underflow=True)
    for _ in range(8): e._adapt(0.0, underflow)
    assert e.degrade == 4
    assert e.synth.max_unison == 2 and not e.synth.aux_on
    for _ in range(48): e._adapt(0.0, None)
    assert e.degrade == 0
    assert e.synth.max_unison == UNI_MAX and e.synth.aux_on


def test_stage_four_alternates_silence_and_audio():
    e = AudioEngine(); e.set_params(default_patch())
    e.degrade = 4; e._apply_degrade()
    e.push("note_on", 60, 0.8)
    out = np.full((BLOCK, 2), np.nan, np.float32)
    e._callback(out, BLOCK, None, None)
    assert np.count_nonzero(out) == 0
    e._callback(out, BLOCK, None, None)
    assert np.isfinite(out).all() and np.count_nonzero(out) > 0

"""Recovery characterization; xfails are OPEN defects, not accepted behaviour.
Run from this synth's directory; never co-import the sibling padsynth packages.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pytest

from padsynth.param import Patch, BY_KEY, list_presets, load_preset, morph_live, default_patch
from padsynth.engine.core import AudioEngine, OfflineEngine, make_engine
from padsynth.engine.synth import ADSR, BLOCK, SR, Biquad, MAX_VOICES
from padsynth.engine.fx import DelayLine
from padsynth.themes import list_themes, load_theme, SEMANTIC

ROOT = Path(__file__).resolve().parents[1]


def engine(seed=73):
    np.random.seed(seed)
    e = OfflineEngine()
    e.set_params(default_patch())
    return e


@pytest.mark.parametrize("path", list_presets(), ids=lambda p: p.stem)
def test_factory_preset_roundtrip_finite_audio(path):
    p = load_preset(path)
    assert Patch.from_dict(json.loads(json.dumps(p.to_dict()))).to_dict() == p.to_dict()
    assert set(p.live()) == set(BY_KEY)
    assert all(np.isfinite(v) and BY_KEY[k].lo <= v <= BY_KEY[k].hi for k, v in p.live().items())
    e = engine()
    e.set_params(p.live())
    e.push("note_on", 60, 0.75)
    a = e.render(4 * BLOCK)
    assert a.shape == (4 * BLOCK, 2)
    assert np.isfinite(a).all()
    assert np.max(np.abs(a)) > 1e-5


@pytest.mark.parametrize("path", list_themes(), ids=lambda p: p.stem)
def test_factory_theme_compiles(path):
    from prompt_toolkit.styles import Style
    skin = load_theme(path)
    Style.from_dict({k: skin.style(k) for k in SEMANTIC})
    assert skin.id


def test_seeded_full_block_render_is_repeatable():
    def render():
        e = engine()
        e.push("note_on", 60, 0.8)
        return e.render(2 * BLOCK)
    np.testing.assert_array_equal(render(), render())


def test_no_audio_engine_does_not_import_native_backend(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    assert isinstance(make_engine(True), OfflineEngine)


def test_voice_capacity_is_bounded():
    e = engine()
    for note in range(40, 80):
        e.push("note_on", note, 0.5)
    e.render(BLOCK)
    assert len(e.synth.voices) == MAX_VOICES
    assert sum(v.active for v in e.synth.voices) <= MAX_VOICES


def test_note_release_and_sustain():
    e = engine()
    e.push("note_on", 60, 0.8)
    e.push("sustain", True)
    e.push("note_off", 60)
    e.render(BLOCK)
    v = next(v for v in e.synth.voices if v.active)
    assert v.held
    e.push("sustain", False)
    e.render(BLOCK)
    assert not v.held and v.amp_env.state in (ADSR.REL, ADSR.OFF)


@pytest.mark.parametrize("mode", [0, 1, 2])
def test_biquad_matches_scipy_reference(mode, monkeypatch):
    import math
    signal = pytest.importorskip("scipy.signal")
    from padsynth.engine import synth
    x = np.random.default_rng(9).normal(size=BLOCK).astype(np.float32)
    w = math.tau * 2300.0 / SR
    c, alpha = math.cos(w), math.sin(w) / (2 * 0.7)
    nums = [((1-c)/2, 1-c, (1-c)/2), (alpha, 0, -alpha), ((1+c)/2, -(1+c), (1+c)/2)]
    ref = signal.lfilter(np.array(nums[mode]) / (1+alpha), [1, -2*c/(1+alpha), (1-alpha)/(1+alpha)], x)
    np.testing.assert_allclose(Biquad().process(x, 2300.0, 0.7, mode), ref, atol=2e-6, rtol=2e-5)
    if hasattr(synth, "_HAS_SCIPY"):
        monkeypatch.setattr(synth, "_HAS_SCIPY", False)
        np.testing.assert_allclose(Biquad().process(x, 2300.0, 0.7, mode), ref, atol=2e-6, rtol=2e-5)


def test_fixed_size_callback_fills_buffer_without_device():
    e = AudioEngine()
    e.set_params(default_patch())
    e.push("note_on", 60, 0.6)
    out = np.full((BLOCK, 2), np.nan, np.float32)
    e._callback(out, BLOCK, None, None)
    assert np.isfinite(out).all()


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="MOD-001: discrete morph interpolates below midpoint")
def test_discrete_morph_selects_a_below_midpoint():
    a, b = default_patch(), default_patch()
    a["osc.unison"], b["osc.unison"] = 1.0, 6.0
    assert morph_live(a, b, 0.25)["osc.unison"] == 1.0


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="MOD-002: note-off uses new transpose rather than note-on identity")
def test_note_off_after_transpose_releases_original_voice():
    e = engine()
    e.push("note_on", 60, 0.8)
    e.render(BLOCK)
    e.push("transpose", 12)
    e.push("note_off", 60)
    e.render(BLOCK)
    assert all(v.amp_env.state in (ADSR.REL, ADSR.OFF) for v in e.synth.voices if v.active)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="MOD-003: partial offline render discards block remainder")
def test_offline_render_preserves_partial_block_remainder():
    e = engine(); e.push("note_on", 60, 0.8)
    full = e.render(2 * BLOCK)
    e = engine(); e.push("note_on", 60, 0.8)
    split = np.concatenate([e.render(BLOCK + 1), e.render(BLOCK - 1)])
    np.testing.assert_array_equal(full, split)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="MOD-004: delay taps run backwards through history")
def test_delay_line_reads_chronological_history():
    line = DelayLine(16)
    line.write(np.arange(8, dtype=np.float32))
    np.testing.assert_array_equal(line.read(4, 4), [4, 5, 6, 7])


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="MOD-005: oversized callback tail is not filled; fixed BLOCK is the normal stream contract")
def test_callback_defensively_fills_oversized_output():
    e = AudioEngine(); e.set_params(default_patch())
    out = np.full((BLOCK + 3, 2), np.nan, np.float32)
    e._callback(out, BLOCK + 3, None, None)
    assert np.isfinite(out).all()


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="MOD-006: preset numeric values are not validated for finiteness")
def test_nonfinite_patch_is_rejected_before_live_dsp():
    try:
        p = Patch.from_dict({"a": {"filter.cut": float("nan")}})
        live = p.live()
    except ValueError:
        return
    assert np.isfinite(list(live.values())).all()


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="MOD-007: demo adds 72 to already-absolute MIDI notes")
def test_demo_generates_only_valid_midi_notes():
    from padsynth.demo import DemoTransport, PATTERNS
    e = engine(); d = DemoTransport(e)
    for pattern in PATTERNS:
        d._play_chord(pattern, 0)
    events = []
    while not e.events.empty():
        events.append(e.events.get_nowait())
    assert events and all(0 <= ev[1] <= 127 for ev in events if ev[0] == "note_on")


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="MOD-008: overlapping same-pitch note-offs repeatedly find the releasing first voice")
def test_two_same_pitch_releases_release_both_voices():
    e = engine()
    for _ in range(2): e.push("note_on", 60, 0.8)
    e.render(BLOCK)
    for _ in range(2): e.push("note_off", 60)
    e.render(BLOCK)
    assert all(v.amp_env.state in (ADSR.REL, ADSR.OFF) for v in e.synth.voices if v.active)


@pytest.mark.parametrize("screen", ["PLAY", "PATCH", "MIX", "LIBRARY"])
def test_headless_screen_render_and_quit(screen, monkeypatch):
    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput
    from padsynth.ui import PadSynthApp
    from padsynth.demo import DemoTransport
    import threading
    # Suppress only the UI refresh thread; paint synchronously and send real key input.
    monkeypatch.setattr(threading.Thread, "start", lambda self: None)
    e = engine()
    with create_pipe_input() as inp, create_app_session(input=inp, output=DummyOutput()):
        app = PadSynthApp(e, load_preset(list_presets()[0]), load_theme(list_themes()[0]),
                          None, DemoTransport(e), argparse.Namespace(), output=DummyOutput())
        app.screen = screen
        app._render()
        assert app.control.text
        inp.send_text("\x11")
        app.run()
        assert not app._running


@pytest.mark.parametrize("key", sorted(BY_KEY))
def test_each_parameter_endpoint_renders_finite(key):
    for value in (BY_KEY[key].lo, BY_KEY[key].hi):
        e = engine()
        live = default_patch(); live[key] = value
        e.set_params(live); e.push("note_on", 60, 0.8)
        assert np.isfinite(e.render(BLOCK)).all(), (key, value)

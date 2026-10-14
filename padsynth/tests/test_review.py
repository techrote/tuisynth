"""Additional preservation review probes for the standalone implementation."""
import copy
import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("standalone_review", ROOT / "padsynth.py")
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, "x"])
def test_numeric_values_rejected(value):
    patch = copy.deepcopy(p.DEFAULT_PATCH)
    patch["nodes"][0]["params"]["saw_mix"] = value
    assert p.validate_patch(patch)


@pytest.mark.parametrize("mutation", [
    lambda d: d["nodes"][0].update(id=[]),
    lambda d: d["nodes"][0].update(type=[]),
    lambda d: d["nodes"][0].update(inputs=["bad"]),
    lambda d: d["nodes"][-1].update(inputs={"in": []}),
], ids=["unhashable-id", "unhashable-type", "nonobject-inputs", "unhashable-target"])
@pytest.mark.xfail(strict=True, raises=(TypeError, AttributeError), reason="PAD-002: malformed graph fields crash validator instead of returning errors")
def test_malformed_graph_returns_diagnostics_not_exception(mutation):
    patch = copy.deepcopy(p.DEFAULT_PATCH); mutation(patch)
    assert p.validate_patch(patch)


def test_zero_duration_clamps_to_documented_minimum():
    audio = p.render_patch(p.DEFAULT_PATCH, [], 0, sr=8000, seed=7)
    assert len(audio[0]) == len(audio[1]) == 800
    assert not any(audio[0]) and not any(audio[1])


def test_no_audio_backend_is_explicit():
    assert p.probe_audio("null")[0] == "null"

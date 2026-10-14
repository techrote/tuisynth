# [TRIO-002] Kit: parameter registry, validation and presets

Work in `techrote/tuisynth` on **TRIO-002** and complete it end-to-end: implementation,
tests, pull request, CI fixes and merge after every automated check is green.

## Depends on

- TRIO-001 (#2) must be closed.

## Read first

1. `trio/AGENTS.md`
2. This issue and all comments
3. `trio/docs/rag/02-AUDIO-ENGINE-CONTRACT.md` sections "Parameters" and "Presets"
4. `trio/docs/rag/01-ARCHITECTURE.md` section "Configuration and user data"
5. `trio/docs/rag/11-LESSONS-FROM-RECOVERY.md` rows MOD-001, MOD-006, PAD-002
6. Reference only: `cpusynth/padsynth/param.py` (how the recovered synth did it, including
   its bugs)

## Objective

A reusable, strictly validated parameter registry and a schema-versioned preset system with
atomic saves, used by every instrument.

## Files

- `trio/kit/src/trio_kit/params.py`: `ParamError(ValueError)`, frozen dataclass `ParamSpec`
  (fields exactly as in TRIO-ENGINE), `ParamRegistry` with:
  `__init__(specs)`, `__getitem__(key) -> ParamSpec`, `__iter__`, `__len__`, `keys()`,
  `defaults() -> dict[str, float]`, `validate_value(key, value) -> tuple[float, str | None]`
  (returns the accepted value and an optional warning; raises `ParamError`),
  `clamp(key, value)`, `to_unit(key, value) -> float`, `from_unit(key, unit) -> float`,
  `format(key, value) -> str`, `morph(a: dict, b: dict, t: float) -> dict`,
  `validate_params(mapping) -> tuple[dict, list[str]]` (complete dict with defaults filled).
  Constructor raises `ParamError` for duplicate keys, `minimum >= maximum`, default out of range,
  `log` curve with `minimum <= 0`, or `choice` without choices.
- `trio/kit/src/trio_kit/presets.py`: `PresetError(ValueError)`, dataclass `Preset(synth, id,
  name, params, extras, tags)`, `parse_preset(data, registry, synth, extras_validator=None) ->
  tuple[Preset, list[str]]`, `preset_to_json(preset) -> str` (sorted keys, 2-space indent),
  `PresetLibrary(registry, synth, factory_package: str, user_dir: Path, extras_validator=None)`
  with `list() -> list[PresetInfo]` (`id, name, source in {"factory","user"}, tags`),
  `load(id) -> tuple[Preset, list[str]]`, `save(preset, overwrite=False)`, `delete(id)` (user
  presets only; factory -> `PresetError`), `rename(id, new_name)`.
- `trio/kit/src/trio_kit/userdata.py`: `user_data_dir(instrument_id, override=None) -> Path`
  (rules from TRIO-ARCH; creates the directory), `atomic_write_text(path, text)`
  (temp file in same dir, `flush` + `os.fsync`, `os.replace`; temp file removed on failure).
- Formatting rules for `format`: unit `Hz` -> `"440 Hz"` below 1,000 and `"5.0 kHz"` at or
  above; unit `s` -> `"120 ms"` below 1 s and `"1.8 s"` at or above; unit `%` (values 0-1) ->
  `"35%"`; `dB` -> `"-3.0 dB"`; `cents` -> `"+12 c"`; `st` -> `"-2 st"`; choice -> the choice
  label; otherwise 2 significant decimals.

## Tests (names are binding; put them in `trio/kit/tests/`)

- `test_params.py`: `test_registry_rejects_invalid_specs`, `test_validate_rejects_nonfinite_and_wrong_types`
  (NaN, inf, -inf, True, "1", None, [1]), `test_out_of_range_is_clamped_with_warning`,
  `test_discrete_and_choice_round_with_warning`, `test_unit_round_trip_linear_log_exp`,
  `test_format_rules`, `test_morph_discrete_switches_at_half` (t in 0, 0.25, 0.49, 0.5, 0.75, 1),
  `test_morph_continuous_respects_curve`
- `test_presets.py`: `test_parse_valid_preset_fills_defaults`, `test_unknown_keys_warn`,
  `test_wrong_synth_rejected`, `test_bad_id_rejected`,
  `test_structural_garbage_returns_preset_error` (parametrise over at least 12 hostile inputs:
  list root, string root, params as list, nested 20 deep, 300 KiB string, non-UTF-8 bytes,
  NaN literal, missing schema, wrong schema, extras not a dict, tags not a list, id not str),
  `test_atomic_save_and_reload`, `test_save_refuses_overwrite_without_flag`,
  `test_factory_presets_cannot_be_deleted` (use a tiny factory package created under
  `tests/` fixtures), `test_user_preset_lists_after_factory`
- `test_userdata.py`: `test_override_dir_used`, `test_atomic_write_leaves_no_temp_on_error`

## Acceptance criteria

- No hostile input raises anything other than `ParamError`/`PresetError`.
- Every behaviour in TRIO-ENGINE "Parameters" and "Presets" is implemented and tested.
- `python trio/tools/check.py --package all` green; both CI workflows green.

## Out of scope

Engine, events, DSP, UI. Do not add instrument parameters.

## Delivery

Follow `trio/AGENTS.md` sections 2-7. Branch `trio-002-params-presets`.

---
synth_id: padsynth
document_id: PAD-ARCH
---
# PadSynth: architecture and source map

## Whole-buffer audition architecture

`main()` loads config, catalog, patch, theme and session; then routes to diagnostics, snapshot,
WAV/demo export or `run_tui()`. `validate_patch()` and `topo_order()` check graph data before
`render_patch()` creates deterministic stereo Python lists. The voice stage is a specialized pad engine:
`_collect_voice_params()` selects its filter/envelope roles; it is not a general arbitrary voice DSP graph.
The bus stage recursively evaluates the supported nodes with memoized buffers in `eval_bus()`.

Signal flow: oscillator/string/noise sources -> per-note low-pass/envelope/modulation -> voice summation
with headroom -> graph bus chorus/delay/reverb/mixer/output -> optional PCM16 WAV serialization.
The renderer clamps sample rate to 4,000-96,000 Hz and duration to 0.1-60 seconds.
Seeded `random.Random` instances derive their seeds from patch identity, MIDI note and the supplied seed.

`audition_async()` snapshots a patch and starts a render worker; a generation counter discards
superseded render results before playback. Playback is single-flight. This is **not** a continuously
running per-note audio callback engine. Starting another audition cancels/replaces the previous audition.
`stop_playback()` uses shared state and a bounded thread join; exhaustive overlap/stop races remain unqualified.

`run_tui()` uses prompt-toolkit frames, conditional tiles, a command palette and cell mouse mapping.
`run_command()` is the central command dispatcher. Themes are TOML data; configuration is explicitly
user-maintained, while small runtime session records are saved separately.

## Source anchors

Paths and symbols below are generated from the preserved Python AST; line numbers refer to the imported bytes.

| Source | Top-level symbols and lines |
|---|---|
| [padsynth.py](../../padsynth.py) | `clamp` (L60); `stable_seed` (L64); `midi_to_freq` (L69); `note_to_midi` (L76); `midi_to_name` (L89); `atomic_write_bytes` (L95); `atomic_write_text` (L102); `_check_param_value` (L259); `validate_patch` (L283); `topo_order` (L356); `patch_node_map` (L388); `adsr_level` (L399); `lfo_shape_value` (L415); `biquad_lp_coeffs` (L428); `_resonance_to_q` (L444); `_collect_voice_params` (L448); `_route_amount` (L471); `_render_voice_note` (L491); `render_dry` (L577); `_apply_chorus` (L605); `_apply_delay` (L627); `_comb_process` (L650); `_allpass_process` (L665); `_apply_reverb` (L677); `_apply_width` (L701); `_apply_softclip` (L712); `eval_bus` (L716); `make_chord` (L792); `render_patch` (L796); `buffer_peak` (L806); `write_wav` (L816); `probe_audio` (L839); `_play_winsound` (L863); `_play_sounddevice` (L884); `_play_spec` (L899); `play_buffer_async` (L912); `_play_spec_async` (L919); `audition_async` (L944); `stop_playback` (L989); `_coerce_bool` (L1024); `load_config` (L1030); `_is_hex` (L1293); `_resolve_palette_color` (L1297); `_normalize_legacy` (L1312); `validate_theme_mapping` (L1342); `discover_themes` (L1674); `load_theme_file` (L1687); `compile_ramps` (L1746); `theme_style_map` (L1771); `quantize_hex` (L1799); `state_dir_for` (L1818); `load_session` (L1824); `save_session` (L1834); `probe_state_lock` (L1840); `check_state_lock` (L1856); `piano_white_midi` (L1923); `piano_key_at` (L1927); `piano_velocity` (L1943); `pad_chord` (L1951); `parity_report` (L2043); `level_glyph` (L2072); `render_snapshot_text` (L2081); `app_base_dir` (L2136); `default_config_path` (L2140); `load_patch_file` (L2144); `list_patch_files` (L2154); `resolve_patch` (L2163); `build_medley` (L2189); `run_demo_text` (L2233); `build_diagnostics` (L2245); `main` (L2281); `TuiState` (L2493); `_row_info` (L2563); `_get_param` (L2579); `_set_param` (L2587); `_frac_to_value` (L2600); `_value_to_frac` (L2608); `_browser_entries` (L2615); `_filtered_commands` (L2626); `run_command` (L2631); `_apply_theme_by_id` (L2948); `run_tui` (L3003) |

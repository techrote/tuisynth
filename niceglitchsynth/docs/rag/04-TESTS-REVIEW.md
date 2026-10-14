---
synth_id: niceglitchsynth
document_id: NG-REVIEW
review_date: 2026-10-14
status: open-defects-preserved
---
# Nice Glitch Synth: tests and review

## Disposition

**Import/preservation accepted; production/audio-device acceptance not established.**
This is a single-reviewer source inspection plus executable characterization, not an independent external audit.
No supplied runtime, factory asset, launcher or pre-existing test was changed. All original project files
are checked against [IMPORT-MANIFEST.json](../IMPORT-MANIFEST.json).

Local final suite: **65 passed, 8 strict expected failures**. See
[test log](../../../evidence/local/niceglitchsynth.txt), [JUnit](../../../evidence/local/niceglitchsynth.xml),
[environment](../../../evidence/local/environment.json) and [packaging evidence](../../../evidence/packaging.json).
Expected failures are open deficiencies, not green functionality. Unexpected passes fail the gate so a
future fix must be reviewed and its expected-failure marker removed. Unrelated failures remain hard failures.

## Coverage and findings

[tests/test_review.py](../../tests/test_review.py) checks every factory preset, every factory theme, deterministic
seeded full-block output, all 43 parameter minima/maxima, voice capacity, sustain/release, SciPy filter-reference
agreement, device-free engine construction, fixed-size callback filling, four headless screens and quit.
No audio stream is opened. The following shared defects are separately reproduced in this implementation:

| ID | Priority | Verified condition / next acceptance |
|---|---|---|
| MOD-001 | P2 | A discrete unison A=1/B=6 at morph 0.25 returns 2.25 instead of selecting A. Define and test discrete endpoint semantics at 0.5 and on both sides. |
| MOD-002 | P1 | Note-off after transpose addresses the new pitch, leaving the originally held voice unreleased. Track note-on identity through transpose changes. |
| MOD-003 | P1 offline | `render(257)` followed by `render(255)` differs from `render(512)` because unused block tails are discarded. Buffer the remainder and test event-boundary semantics. |
| MOD-004 | P1 DSP | After writing 0..7, delay=4/read=4 returns reversed history rather than 4,5,6,7. Resolve chronological delay semantics with explicit impulse/ramp and feedback tests; repair may change the original timbre. |
| MOD-005 | P2 boundary | A callback larger than configured BLOCK leaves its tail untouched. The normal stream explicitly requests BLOCK=256, so this is a defensive contract gap, not evidence that the ordinary device callback varies. Require full initialization or explicit safe rejection. |
| MOD-006 | P1 imported data | NaN in a known patch parameter reaches the live dictionary. Add finite/type/schema validation before DSP without silent coercion. |
| MOD-007 | P1 demo | Demo transport adds 72 to already-absolute MIDI roots and emits values above 127. Establish intended demo register with owner listening and enforce valid event bounds. |
| MOD-008 | P1 voices | Two same-pitch note-offs select the already-releasing first voice, leaving the second voice gated. Use explicit gate/voice ownership and test repeated overlapping notes. |
| MOD-PKG-001 | P2 distribution | Wheel creation succeeds, but wheel contents omit `presets/` and `themes/`; factory-theme lookup prevents a normal standalone installed-wheel launch. Package resources and test installation outside the source tree. |

The issue IDs are shared contracts, not proof that fixing one folder fixes the other. Preserve each identity.

`tests/test_degradation.py` adds two passing policy tests for pressure escalation/recovery and alternating
silence at stage four. Bypassing effects and intentionally skipping blocks are preserved characteristics,
not folded into the shared bug list. An offline render does not qualify their real-device timing behaviour.

## Additional static observations, not completed acceptance claims

The UI/DSP parameter swap, rapid demo restart/stop, stream-start failure cleanup, master peaks after DC
blocking, waveform/LFO continuity, unused parameter paths and hostile nested theme data need further work.
These are bounded review concerns, not independently qualified fixes or a complete security audit.
The inherited assertions about guaranteed safe themes, a limiter, and survival under any load are not proven.

The callback contract reference is [python-sounddevice's stream documentation](https://python-sounddevice.readthedocs.io/en/latest/api/streams.html):
output must be initialized and callback exceptions do not propagate normally to the main application.

## Publication and physical gates

A passing preservation CI means original hashes and the declared characterization baseline hold.
It does not mean the expected failures were fixed, packaging was certified or playback is safe at arbitrary gain.
Physical audio output, MIDI hardware, real Windows Terminal mouse/drag behaviour, sustained low-latency load,
perceptual quality and operating-system-specific launcher execution remain untested locally.

Build-discovery reference: [setuptools package discovery](https://setuptools.pypa.io/en/latest/userguide/package_discovery.html).
Headless input/output reference: [prompt-toolkit API](https://python-prompt-toolkit.readthedocs.io/en/master/pages/reference.html).

# TRIO: three terminal pad / air / string synthesizers

**Status: planned.** This folder holds the design authority and implementation programme for
three new, deliberately different TUI synthesizers on a shared foundation. Code arrives
through the dependency-ordered `[TRIO-0NN]` GitHub issues.

| Instrument | Sound | Synthesis | Signature gesture |
|---|---|---|---|
| **AURORA** (`aurora`) | lush evolving pads | Nasca PADsynth spectral wavetables | paint the harmonic spectrum |
| **LOOM** (`loom`) | plucked, strummed and bowed strings | digital waveguides + sympathetic strings + bodies | strum across vibrating strings |
| **DRIFT** (`drift`) | breath, wind, vowel clouds | granular synthesis + formant filters | steer a storm over a weather map |

All three: mouse-first with a keyboard twin for every action, artistic ASCII/Unicode
interfaces, live-switchable skins, an on-screen clickable keyboard, computer-keyboard notes and
USB MIDI. Stretch goals: step sequencer/arpeggiator and modulation oscillators with a
post-processing rack.

## Read

- [Charter and difference contract](docs/rag/00-CHARTER.md)
- [Implementation programme and issue catalogue](docs/programme/IMPLEMENTATION-PROGRAMME.md)
- [RAG index](docs/rag/INDEX.md)
- [Agent execution contract](AGENTS.md)
- [Provenance ledger](docs/PROVENANCE.md)

The preserved recovered synths (`../cpusynth`, `../padsynth`, `../niceglitchsynth`) are
reference material only; their review findings are mapped to TRIO contracts in
[11-LESSONS-FROM-RECOVERY.md](docs/rag/11-LESSONS-FROM-RECOVERY.md).

## Development

Set up by TRIO-001. Until then there is no code to run.

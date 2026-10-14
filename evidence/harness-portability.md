# Headless review harness portability correction

The first PR CI run, `38600100320`, passed on Ubuntu/Python 3.11 but stalled
in the modular synths' Windows headless tests. The newly added tests replaced
`threading.Thread.start` globally to suppress UI refresh. That replacement also
suppresses prompt-toolkit's Windows input-wait executor, preventing the queued
Ctrl+Q from reaching the application. This is a review-harness defect, not an
original synth defect, and is not added to the known-product xfail list.

The correction mocks only `PadSynthApp._refresh_loop`, leaving Python threading
and prompt-toolkit input handling intact. The four screens are still rendered
and closed through pipe input; no test is skipped or changed to expected failure.
Original synth sources and their SHA-256 identities remain untouched.

Authoritative hosted results are the subsequent PR checks on the corrected head.
The committed local results preceded this harness-only correction; an additional
local execution of all three suites after correction retained the same totals:
CPU Synth 63 passed / 8 xfailed, PadSynth 52 / 5, Nice Glitch 65 / 8.

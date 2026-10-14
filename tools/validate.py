"""Run isolated preservation suites without opening audio or MIDI devices."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SYNTHS = ("cpusynth", "padsynth", "niceglitchsynth")


def verify_originals():
    count = 0
    for name in SYNTHS:
        data = json.loads((ROOT / name / "docs" / "IMPORT-MANIFEST.json").read_text())
        for item in data["retained_files"]:
            path = ROOT / name / item["path"]
            raw = path.read_bytes()
            if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise ValueError(f"Preserved original changed: {name}/{item['path']}")
            count += 1
    print(f"Verified {count} byte-identical original project files", flush=True)
    return count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=ROOT / "evidence" / "ci")
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()
    count = verify_originals()
    if args.verify_only:
        return 0
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    report = {"python": sys.version, "platform": platform.platform(), "preserved_files": count,
              "hardware_audio_tested": False, "midi_hardware_tested": False, "packages": {}, "suites": {}}
    for package in ("numpy", "scipy", "prompt-toolkit", "wcwidth", "pytest", "setuptools"):
        try: report["packages"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: report["packages"][package] = "not installed"
    for name in SYNTHS:
        command = [sys.executable, "-m", "pytest", "-q", "-rx", "tests", f"--junitxml={out / (name + '.xml')}"]
        try:
            process = subprocess.run(command, cwd=ROOT / name, text=True, encoding="utf-8",
                                     errors="replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     timeout=180, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            (out / (name + ".txt")).write_text(process.stdout, encoding="utf-8")
            report["suites"][name] = {"exit_code": process.returncode, "command": command}
            print(f"[{name}] exit={process.returncode}\n{process.stdout}", flush=True)
        except subprocess.TimeoutExpired:
            report["suites"][name] = {"exit_code": 124, "error": "180 second limit exceeded"}
    (out / "environment.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return int(any(s["exit_code"] != 0 for s in report["suites"].values()))


if __name__ == "__main__":
    raise SystemExit(main())

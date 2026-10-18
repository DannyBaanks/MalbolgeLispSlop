#!/usr/bin/env python3
"""Capture suite and pre-existing evidence verification without altering them."""
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    commands = [("unittest", [sys.executable, "-m", "unittest", "discover"], ROOT)]
    commands.extend((f"manifest_m{i}", ["sha256sum", "-c", "SHA256SUMS.txt"],
                     ROOT / f"evidence/specimen100/m{i}") for i in range(5))
    targets = [HERE / f"{name}.{stream}.txt" for name, _, _ in commands
               for stream in ("stdout", "stderr")]
    targets.append(HERE / "execution.json")
    if any(p.exists() for p in targets):
        raise SystemExit("Refusing reuse of evidence output paths")
    runs = []
    for name, command, cwd in commands:
        cp = subprocess.run(command, cwd=cwd, capture_output=True, timeout=180)
        (HERE / f"{name}.stdout.txt").write_bytes(cp.stdout)
        (HERE / f"{name}.stderr.txt").write_bytes(cp.stderr)
        runs.append({"name": name, "command": command, "cwd": str(cwd),
                     "exit": cp.returncode,
                     "stdout_sha256": hashlib.sha256(cp.stdout).hexdigest(),
                     "stderr_sha256": hashlib.sha256(cp.stderr).hexdigest()})
    out = {"utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "runs": runs, "all_commands_exit_zero": all(r["exit"] == 0 for r in runs)}
    (HERE / "execution.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    raise SystemExit(0 if out["all_commands_exit_zero"] else 1)


if __name__ == "__main__":
    main()

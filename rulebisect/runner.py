from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path


def run_process(argv: list[str], cwd: Path, log: Path, timeout: int, stdin: str | None = None) -> dict:
    """No shell. Kill the process group on POSIX timeout or interruption."""
    start = time.monotonic()
    with log.open("wb") as output:
        try:
            process = subprocess.Popen(argv, cwd=cwd, stdout=output, stderr=subprocess.STDOUT,
                                       stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                       start_new_session=os.name == "posix")
        except OSError as error:
            return {"status": "error", "error": str(error), "seconds": 0}
        try:
            process.communicate(None if stdin is None else stdin.encode(), timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            process.wait()
            if isinstance(error, KeyboardInterrupt):
                raise
            return {"status": "timeout", "seconds": round(time.monotonic() - start, 3)}
    return {"status": "completed", "exit_code": process.returncode,
            "seconds": round(time.monotonic() - start, 3)}


def codex_command(model: str | None) -> list[str]:
    command = ["codex", "exec", "--json", "--ephemeral", "--ignore-user-config",
               "--sandbox", "workspace-write", "-c", 'approval_policy="never"', "-"]
    if model:
        command[2:2] = ["--model", model]
    return command


def codex_metadata(log: Path) -> dict:
    usage, models = [], []
    for line in log.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("usage"):
            usage.append(event["usage"])
        if event.get("model"):
            models.append(event["model"])
    return {"reported_usage": usage, "reported_models": models}

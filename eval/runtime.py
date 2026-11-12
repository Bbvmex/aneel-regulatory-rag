"""Shared helpers for local evaluation runs: GPU temperature, llama-server health, git state."""

import subprocess
import time
import urllib.request


def gpu_temp() -> int | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return int(out.strip().splitlines()[0])
    except (OSError, subprocess.CalledProcessError, ValueError, IndexError):
        return None


def wait_below(limit: int) -> None:
    # The laptop overheats: never queue work on a hot GPU.
    while (t := gpu_temp()) is not None and t > limit:
        time.sleep(10)


def wait_healthy(base_url: str, proc: subprocess.Popen, timeout_s: float = 900) -> None:
    health = base_url.rstrip("/").removesuffix("/v1") + "/health"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"llama-server exited with code {proc.returncode}")
        try:
            with urllib.request.urlopen(health, timeout=5) as resp:
                if resp.status == 200:
                    return
        except OSError:
            pass
        time.sleep(5)
    raise TimeoutError("llama-server did not become healthy")


def git_state() -> tuple[str, bool]:
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
    ).stdout
    # New, uncommitted reports do not change the code that runs.
    dirty = any(line and not line.startswith("?? eval/reports/") for line in status.splitlines())
    return sha, dirty

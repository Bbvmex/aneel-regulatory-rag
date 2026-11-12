"""python -m aneel_rag.llm.server: verify the pinned GGUF and build, then run llama-server."""

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from aneel_rag.config.settings import (
    PROJECT_ROOT,
    AppConfig,
    LocalLLMConfig,
    file_sha256,
    get_secrets,
    load_config,
)

HASH_CACHE = PROJECT_ROOT / "data" / "cache" / "gguf_sha256.json"


class PinMismatchError(RuntimeError):
    pass


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p


def verify_gguf(path: Path, expected: str, cache: Path = HASH_CACHE) -> None:
    """Hash once per (path, size, mtime): a 20 GB file takes a minute to hash."""
    if not path.is_file():
        raise PinMismatchError(f"{path} not found; download it from the gguf_repo in config")
    stat = path.stat()
    key = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    known = json.loads(cache.read_text("utf-8")) if cache.is_file() else {}
    digest = known.get(key)
    if digest is None:
        digest = file_sha256(path)
        known[key] = digest
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(known, indent=1), "utf-8")
    if digest != expected:
        raise PinMismatchError(f"{path.name}: sha256 {digest} != pinned {expected}")


def parse_build(version_output: str) -> str | None:
    match = re.search(r"build (\d+)", version_output)
    return f"b{match.group(1)}" if match else None


def check_build(binary: str, expected: str) -> None:
    out = subprocess.run([binary, "--version"], capture_output=True, text=True, check=False)
    build = parse_build(out.stdout + out.stderr)
    if build != expected:
        raise PinMismatchError(f"{binary} is build {build}, config pins {expected}")


def server_argv(local: LocalLLMConfig, binary: str, gguf: Path, alias: str, port: int) -> list[str]:
    # The alias makes /v1/models report the configured generator ID.
    return [
        binary,
        "-m",
        str(gguf),
        "--alias",
        alias,
        "--port",
        str(port),
        "-c",
        str(local.ctx_size),
        "-t",
        str(local.threads),
        "-fa",
        local.flash_attn,
        "--fit",
        "on",
        "--fit-target",
        str(local.fit_target_mib),
        "--reasoning",
        local.reasoning,
        "--no-webui",
    ]


def port_of(base_url: str) -> int:
    return urlparse(base_url).port or 8080


def prepare(cfg: AppConfig, local: LocalLLMConfig | None = None) -> list[str]:
    """Verify the pins and return the server command; `local` overrides cfg.local_llm."""
    local = local or cfg.local_llm
    secrets = get_secrets()
    gguf = _resolve(secrets.gguf_dir) / local.gguf_file
    verify_gguf(gguf, local.gguf_sha256)
    check_build(secrets.llama_server_bin, local.llama_cpp_build)
    alias = cfg.models.generator if local == cfg.local_llm else Path(local.gguf_file).stem
    port = port_of(secrets.local_llm_base_url or "http://localhost:8080/v1")
    return server_argv(local, secrets.llama_server_bin, gguf, alias, port)


def main() -> int:
    try:
        argv = prepare(load_config())
    except PinMismatchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(" ".join(argv), flush=True)
    return subprocess.run(argv, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())

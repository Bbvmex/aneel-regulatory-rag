import hashlib
import json

import pytest

from aneel_rag.config import load_config
from aneel_rag.llm.server import (
    PinMismatchError,
    parse_build,
    port_of,
    server_argv,
    verify_gguf,
)


def test_parse_build_reads_the_build_number():
    out = "version: 0.9.0-dev (build 12110, commit cd959bae9)\nbuilt with Clang"
    assert parse_build(out) == "b12110"
    assert parse_build("no version here") is None


def test_server_argv_carries_the_pinned_flags(tmp_path):
    local = load_config().local_llm
    argv = server_argv(local, "llama-server", tmp_path / "m.gguf", "alias-x", 8081)
    joined = " ".join(argv)
    assert argv[0] == "llama-server"
    assert f"-c {local.ctx_size}" in joined
    assert f"--reasoning {local.reasoning}" in joined
    assert f"--fit-target {local.fit_target_mib}" in joined
    assert "--alias alias-x" in joined and "--port 8081" in joined


def test_port_of_endpoint():
    assert port_of("http://localhost:8081/v1") == 8081
    assert port_of("http://localhost/v1") == 8080


def test_verify_gguf_checks_and_caches_the_hash(tmp_path):
    gguf, cache = tmp_path / "m.gguf", tmp_path / "cache.json"
    gguf.write_bytes(b"weights")
    digest = hashlib.sha256(b"weights").hexdigest()
    verify_gguf(gguf, digest, cache)
    assert list(json.loads(cache.read_text("utf-8")).values()) == [digest]
    with pytest.raises(PinMismatchError, match="pinned"):
        verify_gguf(gguf, "0" * 64, cache)


def test_verify_gguf_missing_file(tmp_path):
    with pytest.raises(PinMismatchError, match="not found"):
        verify_gguf(tmp_path / "absent.gguf", "0" * 64, tmp_path / "c.json")

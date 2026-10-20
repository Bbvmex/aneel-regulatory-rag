import re

import pytest

from aneel_rag.config import file_sha256
from aneel_rag.config.settings import PROJECT_ROOT

RAW = PROJECT_ROOT / "data" / "raw"
ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(?:yes|no)\s*\|\s*`([0-9a-f]{64})`\s*\|", re.M)


def _declared() -> list[tuple[str, str]]:
    return ROW.findall((RAW / "SOURCE.md").read_text(encoding="utf-8"))


def test_source_manifest_declares_hashes():
    assert _declared(), "SOURCE.md must list at least one file hash"


@pytest.mark.parametrize("name,expected", _declared())
def test_declared_hash_matches_local_file(name, expected):
    # Full HTML and PDF are not versioned, so CI only checks files that exist.
    path = RAW / name
    if not path.exists():
        pytest.skip(f"{name} not present locally")
    assert file_sha256(path) == expected

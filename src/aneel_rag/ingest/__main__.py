"""python -m aneel_rag.ingest: parse the law-content extract into data/processed."""

import json
import sys
from datetime import date
from pathlib import Path

from aneel_rag.config.settings import PROJECT_ROOT, file_sha256, load_config
from aneel_rag.ingest import html_load, report
from aneel_rag.ingest.models import PARSER_VERSION, Manifest
from aneel_rag.ingest.pipeline import parse_extract

OUT = PROJECT_ROOT / "data" / "processed"


def write_units(units, path: Path) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for unit in units:
            fh.write(json.dumps(unit.model_dump(mode="json"), ensure_ascii=False) + "\n")


def main() -> int:
    cfg = load_config()
    corpus = cfg.corpus.path if cfg.corpus.path.is_absolute() else PROJECT_ROOT / cfg.corpus.path
    root = html_load.load_extract(corpus)
    result = parse_extract(root, cfg)
    OUT.mkdir(parents=True, exist_ok=True)
    write_units(result.units, OUT / "units.jsonl")
    manifest = Manifest(
        corpus_path=cfg.corpus.path.as_posix(),
        corpus_sha256=file_sha256(corpus),
        parser_version=PARSER_VERSION,
        generated_on=date.today().isoformat(),
        units=len(result.units),
        preamble=result.preamble,
        footer=result.footer,
    )
    (OUT / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md = report.render(result, root, manifest)
    (OUT / "ingest_report.md").write_text(md, encoding="utf-8")
    problems = report.blocking_problems(result)
    print(f"{len(result.units)} units -> {OUT}")
    for problem in problems:
        print(f"ERROR: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

"""python -m aneel_rag.retrieval.query "pergunta" --mode hybrid+rerank: inspect retrieval."""

import argparse
import sys

from aneel_rag.config.settings import load_config
from aneel_rag.retrieval.hub import ModelNotCachedError
from aneel_rag.retrieval.index import collection_name, make_client, make_embedder
from aneel_rag.retrieval.modes import MODES
from aneel_rag.retrieval.provenance import IndexMismatchError, check_index, expected_provenance
from aneel_rag.retrieval.reranker import BGEReranker
from aneel_rag.retrieval.retriever import Retriever


def main(argv: list[str] | None = None) -> int:
    cfg = load_config()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--mode", choices=MODES, default=cfg.retrieval.mode)
    parser.add_argument("-k", type=int, default=cfg.retrieval.k_final)
    parser.add_argument("--include-revoked", action="store_true")
    parser.add_argument("--include-annexes", action="store_true")
    args = parser.parse_args(argv)

    # Fail on a stale index before loading any model.
    client, collection = make_client(), collection_name(cfg)
    try:
        check_index(client, collection, expected_provenance(cfg))
    except IndexMismatchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    try:
        reranker = None
        if args.mode == "hybrid+rerank":
            reranker = BGEReranker(
                cfg.models.reranker,
                cfg.models.reranker_revision,
                cfg.embedding.rerank_max_length,
                cfg.embedding.batch_size,
            )
        embedder = make_embedder(cfg)
    except ModelNotCachedError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    retriever = Retriever(client, collection, embedder, cfg.retrieval, reranker)
    hits = retriever.search(
        args.query,
        mode=args.mode,
        k=args.k,
        include_revoked=args.include_revoked or None,
        include_annexes=args.include_annexes or None,
    )
    for hit in hits:
        c = hit.chunk
        preview = " ".join(c.text.split())[:240]
        print(f"{hit.rank}. [{hit.score:.4f}] {c.chunk_id} ({c.status}, {c.doc_type})")
        print(f"   units: {', '.join(c.unit_ids[:8])}{' …' if len(c.unit_ids) > 8 else ''}")
        print(f"   {preview}")
    return 0 if hits else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

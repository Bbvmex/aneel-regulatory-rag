"""Reranker diagnosis (decision 26): pair lengths, padding, threads, batch size and loop overhead.

Prints a table for review; it is not an evaluation report and its numbers stay out of the docs.
Usage: uv run python scripts/diagnose_reranker.py [--n 12]
"""

import argparse
import json
import random
import statistics
import sys
import time

import torch

from aneel_rag.config.settings import PROJECT_ROOT, load_config
from aneel_rag.retrieval.index import collection_name, make_client, make_embedder
from aneel_rag.retrieval.provenance import expected_provenance
from aneel_rag.retrieval.reranker import BGEReranker
from aneel_rag.retrieval.retriever import Retriever


def manual_scores(flag, query: str, texts: list[str], max_length: int, batch_size: int):
    """Sorted by length, padded to the longest pair of each batch, no batch-size probe."""
    tok, model = flag.tokenizer, flag.model
    enc = [
        tok(query, t, truncation="only_second", max_length=max_length)["input_ids"] for t in texts
    ]
    order = sorted(range(len(enc)), key=lambda i: -len(enc[i]))
    scores = [0.0] * len(enc)
    with torch.inference_mode():
        for start in range(0, len(order), batch_size):
            idx = order[start : start + batch_size]
            batch = tok.pad({"input_ids": [enc[i] for i in idx]}, return_tensors="pt")
            logits = model(**batch, return_dict=True).logits.view(-1).float()
            for i, s in zip(idx, torch.sigmoid(logits).tolist(), strict=True):
                scores[i] = s
    return scores, [len(e) for e in enc]


def padded_tokens(lengths: list[int], batch_size: int) -> int:
    ordered = sorted(lengths, reverse=True)
    return sum(
        max(ordered[i : i + batch_size]) * len(ordered[i : i + batch_size])
        for i in range(0, len(ordered), batch_size)
    )


def timed(fn):
    t0 = time.perf_counter()
    out = fn()
    return out, time.perf_counter() - t0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=12, help="validated questions to sample")
    parser.add_argument("--seed", type=int, default=26)
    args = parser.parse_args()

    cfg = load_config()
    rows = [
        json.loads(line)
        for line in (PROJECT_ROOT / "eval" / "dataset.jsonl").read_text("utf-8").splitlines()
    ]
    rows = [r for r in rows if r["status"] == "validated"]
    questions = [r["question"] for r in random.Random(args.seed).sample(rows, args.n)]

    max_len = cfg.embedding.rerank_max_length
    reranker = BGEReranker(
        cfg.models.reranker, cfg.models.reranker_revision, max_len, cfg.embedding.rerank_batch_size
    )
    from FlagEmbedding import FlagReranker

    flag = FlagReranker(
        str(reranker._model.name_or_path),
        use_fp16=False,
        devices="cpu",
        max_length=max_len,
        batch_size=cfg.embedding.batch_size,
    )
    flag.model.eval()
    retriever = Retriever(
        make_client(),
        collection_name(cfg),
        make_embedder(cfg),
        cfg.retrieval,
        reranker,
        expected=expected_provenance(cfg),
    )
    pools = [[h.chunk.text for h in retriever.candidates(q)] for q in questions]

    print(f"torch {torch.__version__}: intra-op threads {torch.get_num_threads()}, ")
    print(f"interop {torch.get_num_interop_threads()}; questions {len(questions)}; ")
    print(f"pool k_candidates {cfg.retrieval.k_candidates}; rerank_max_length {max_len}\n")

    lengths, results = [], {}
    batch_sizes = sorted({1, 4, cfg.embedding.batch_size, cfg.retrieval.k_candidates})
    for q, texts in zip(questions, pools, strict=True):
        flag_scores, t = timed(
            lambda q=q, texts=texts: flag.compute_score([(q, x) for x in texts], normalize=True)
        )
        results.setdefault("FlagReranker.compute_score", []).append(t)
        _, t = timed(lambda q=q, texts=texts: reranker.score(q, texts))
        results.setdefault("BGEReranker.score (configured)", []).append(t)
        for bs in batch_sizes:
            (scores, lens), t = timed(
                lambda q=q, texts=texts, bs=bs: manual_scores(flag, q, texts, max_len, bs)
            )
            results.setdefault(f"manual loop, batch {bs}", []).append(t)
            diff = max(abs(a - b) for a, b in zip(scores, flag_scores, strict=True))
            results.setdefault(f"max |score diff| batch {bs}", []).append(diff)
        lengths.append(lens)
        for cut in (512, 1024):
            (_, _), t = timed(
                lambda q=q, texts=texts, cut=cut: manual_scores(
                    flag, q, texts, cut, cfg.embedding.batch_size
                )
            )
            results.setdefault(f"manual loop, max_length {cut}", []).append(t)

    flat = [n for lens in lengths for n in lens]
    print("Tokens per (query, chunk) pair:")
    print(
        f"  min {min(flat)}, median {statistics.median(flat):.0f}, max {max(flat)}, "
        f"> 512: {sum(n > 512 for n in flat)}/{len(flat)}, "
        f"> 1024: {sum(n > 1024 for n in flat)}/{len(flat)}"
    )
    for bs in batch_sizes:
        real = sum(flat)
        padded = sum(padded_tokens(lens, bs) for lens in lengths)
        print(f"  batch {bs}: padding adds {100 * (padded - real) / real:.1f}% tokens")
    print("\nSeconds per question (median, max) and score agreement:")
    for name, values in results.items():
        if name.startswith("max |"):
            print(f"  {name}: {max(values):.2e}")
        else:
            print(f"  {name}: {statistics.median(values):.2f} s, max {max(values):.2f} s")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

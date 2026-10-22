# ADR-003: Hybrid retrieval with Qdrant, RRF fusion and cross-encoder reranking

- **Status:** accepted
- **Date:** 2026-10-22

## Context
Questions about REN 1.000/2021 mix two styles: paraphrased ("can the utility cut my power without
warning?") and lexical, with exact terms, numbers and device labels ("prazo de religação",
"art. 362"). Pure dense retrieval misses exact terms; pure lexical retrieval misses paraphrases.
Everything must run on CPU, and CI runs without models.

## Decision
- **One model for both signals.** `BAAI/bge-m3` produces a dense vector (1024 dimensions,
  cosine) and lexical weights per token, stored as a Qdrant sparse vector. One forward pass per
  chunk gives both. No IDF modifier is applied to the sparse vector: the weights are learned.
- **Collection layout.** Named vectors `dense` and `sparse`. The payload is the whole chunk
  (`chunk_id`, `text`, `unit_ids`, `article_id`, `article_ids`, `doc_type`, `status`,
  `strategy`), with keyword indexes on `status` and `doc_type`. Point IDs are UUIDv5 of the
  `chunk_id`, so re-indexing is idempotent. There is one collection per chunking strategy:
  `<qdrant.collection>_<chunking.strategy>` (for example `ren1000_v1_structural`).
- **Modes** (`retrieval.mode`, overridable per call):
  - `dense` and `sparse`: one query on that vector, top `k_final`;
  - `hybrid`: two prefetches (`k_dense`, `k_sparse`) fused server-side by Qdrant with
    Reciprocal Rank Fusion (`FusionQuery(RRF)`), top `k_final`;
  - `hybrid+rerank`: the hybrid pool of `k_candidates` (20) is rescored by the cross-encoder
    `BAAI/bge-reranker-v2-m3` (normalized scores), top `k_final` (5).
- **Default filter.** `status != revoked` and `doc_type == norm`, applied to every prefetch and to
  the final query. `include_revoked` and `include_annexes` lift each condition.
- **Token limits.** `embedding.max_length` and `embedding.rerank_max_length` are 2048 tokens.
  The longest structural chunk is about 4k characters, so nothing is truncated. The reranker's
  library default (512) would cut most long chunks.
- **Embedding cache.** Document embeddings are cached in SQLite (`data/cache/embeddings.sqlite`,
  not versioned), keyed by SHA-256 of model ID, `max_length` and chunk text. Re-indexing after a
  chunking change only embeds the chunks whose text changed. Queries are not cached.
- **Testing without models.** `HashEmbedder` (hashed bag of words) and `OverlapReranker` (word
  overlap) implement the same protocols. CI runs every mode against Qdrant `:memory:` with them.
  Real models are loaded lazily, so CI never imports FlagEmbedding or torch.

## Alternatives considered
- **Client-side fusion.** It works, but Qdrant's native RRF is one round trip and has no code to
  get wrong.
- **BM25 sparse vectors (FastEmbed) next to bge-m3 dense.** That is a second model and a
  tokenizer to maintain. The bge-m3 lexical weights fill the same role and stay in one pass.
- **ColBERT vectors from bge-m3.** They are much larger on disk and in memory; the reranker
  already gives late-interaction quality on the top 20.

## Consequences
- Comparing modes in the phase 5 ablation needs only a config change, not re-indexing.
- `k_candidates` bounds reranking latency on CPU (20 pairs per query).
- Payload indexes have no effect in Qdrant `:memory:`; the filters still work there, only without
  the index.

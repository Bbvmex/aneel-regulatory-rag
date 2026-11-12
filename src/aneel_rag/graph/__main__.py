"""python -m aneel_rag.graph "pergunta": answer with validated citations, or abstain."""

import argparse
import sys

import openai

from aneel_rag.config.settings import load_config
from aneel_rag.graph.build import ask, build_graph, nodes_from_config
from aneel_rag.llm.factory import MissingEndpointError
from aneel_rag.retrieval.hub import ModelNotCachedError
from aneel_rag.retrieval.index import StaleProcessedError
from aneel_rag.retrieval.provenance import IndexMismatchError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--json", action="store_true", help="print the full FinalAnswer as JSON")
    args = parser.parse_args(argv)

    try:
        nodes = nodes_from_config(load_config())
    except (
        StaleProcessedError,
        IndexMismatchError,
        MissingEndpointError,
        ModelNotCachedError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    try:
        final = ask(build_graph(nodes), args.question)
    except openai.APIError as exc:  # after the client's own retries with backoff
        print(f"ERROR: LLM call failed: {exc}", file=sys.stderr)
        return 3
    if args.json:
        print(final.model_dump_json(indent=2))
        return 0

    print(final.answer)
    for c in final.citations:
        flag = "" if c.verdict == "valid" else f" [{c.verdict}: {c.reason}]"
        print(f'\n- {c.unit_id}{flag}\n  "{c.quote}"\n  {c.source_url or "(no link)"}')
    if final.abstained:
        print(f"\n(abstention: {final.abstention_reason})")
        for s in final.snippets:
            preview = " ".join(s.text.split())[:240]
            print(f"\n- {s.chunk_id}: {preview}\n  {s.source_url or '(no link)'}")
    print(f"\ntrace_id={final.trace_id} attempts={final.attempts}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

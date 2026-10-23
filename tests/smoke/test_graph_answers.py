"""Full graph against the local index, models and the configured generator (make smoke)."""

import pytest

from aneel_rag.config import get_secrets, load_config
from aneel_rag.graph.build import ask, build_graph, nodes_from_config
from aneel_rag.retrieval.provenance import IndexMismatchError

pytestmark = pytest.mark.smoke

ANSWERABLE = (
    "Qual o prazo para a distribuidora religar a unidade consumidora em área urbana "
    "após a suspensão por falta de pagamento?"
)
# Near miss: electricity bills carry ICMS, but its rate is state law, not REN 1.000/2021.
OUT_OF_SCOPE = "Qual é a alíquota do ICMS cobrada na conta de luz em São Paulo?"


@pytest.fixture(scope="module")
def graph():
    if not get_secrets().llm_api_key:
        pytest.skip("no LLM_API_KEY in .env")
    try:
        nodes = nodes_from_config(load_config())
    except IndexMismatchError as exc:
        pytest.skip(f"index not ready ({exc}); run `make qdrant-up` and `make index`")
    return build_graph(nodes)


def test_answerable_question_has_a_valid_citation(graph):
    final = ask(graph, ANSWERABLE)
    assert not final.abstained, final.abstention_reason
    assert any(c.verdict == "valid" for c in final.citations), final.citations


def test_out_of_scope_question_abstains(graph):
    final = ask(graph, OUT_OF_SCOPE)
    assert final.abstained
    assert final.snippets

"""Policy D6: quote length, verbatim match, context membership and most specific unit."""

import pytest

from aneel_rag.graph.citations import CitationValidator, normalize, normalize_quote
from aneel_rag.graph.schemas import AnswerSchema, Citation
from aneel_rag.ingest.models import Unit


def _unit(uid, parent, text, kind):
    return Unit(
        id=uid,
        parent_id=parent,
        article_id="art-10" if uid.startswith("art-10") else "art-11",
        kind=kind,
        label=uid,
        hierarchy_path=["TÍTULO I — GERAL", uid],
        text=text,
        source_anchor=f"{uid}#0",
        source_url=f"https://example.org/#{uid}",
        doc_type="norm",
        status="active",
    )


UNITS = {
    u.id: u
    for u in [
        _unit(
            "art-10",
            None,
            "Art. 10. A distribuidora deve “religar” a unidade consumidora em até 24 horas.",
            "caput",
        ),
        _unit(
            "art-10-p1",
            "art-10",
            "§ 1º O prazo de religação de urgência é de 4 horas — contado da solicitação.",
            "par",
        ),
        _unit(
            "art-10-p1-inc-I",
            "art-10-p1",
            "I - na área urbana, quando houver pagamento do débito;",
            "inc",
        ),
        _unit(
            "art-11", None, "Art. 11. O consumidor pode solicitar a vistoria do medidor.", "caput"
        ),
    ]
}
CONTEXT = {"art-10", "art-10-p1", "art-10-p1-inc-I"}


@pytest.fixture
def validator():
    return CitationValidator(UNITS, min_chars=20, max_chars=300)


def _check(validator, unit_id, quote, context=CONTEXT):
    return validator.check(Citation(unit_id=unit_id, quote=quote), context)


def test_unknown_unit_is_invalid(validator):
    check = _check(validator, "art-999", "religar a unidade consumidora")
    assert check.verdict == "invalid"
    assert "does not exist" in check.reason


def test_unit_outside_retrieved_context_is_invalid(validator):
    check = _check(validator, "art-11", "solicitar a vistoria do medidor")
    assert check.verdict == "invalid"
    assert "not in the retrieved context" in check.reason


def test_whitespace_quote_marks_and_case_do_not_matter(validator):
    check = _check(validator, "art-10", 'deve  "Religar"\n a unidade consumidora em até 24 horas')
    assert check.verdict == "valid"
    assert check.matched_unit_id == "art-10"
    assert check.source_url == "https://example.org/#art-10"


def test_dash_variants_and_edge_ellipsis_are_unified(validator):
    check = _check(validator, "art-10-p1", "...urgência é de 4 horas - contado da solicitação…")
    assert check.verdict == "valid"


def test_paraphrase_is_invalid(validator):
    check = _check(validator, "art-10", "a distribuidora precisa religar a unidade em um dia")
    assert check.verdict == "invalid"
    assert "verbatim" in check.reason


def test_inner_ellipsis_is_invalid(validator):
    # A gap inside the quote joins non-contiguous text.
    check = _check(validator, "art-10", "A distribuidora deve ... em até 24 horas")
    assert check.verdict == "invalid"


@pytest.mark.parametrize("quote", ["religar a unidade", "x" * 301])
def test_quote_length_outside_bounds_is_invalid(validator, quote):
    unit = UNITS["art-10"].model_copy(update={"text": "x" * 400})
    validator = CitationValidator({**UNITS, "art-10": unit}, 20, 300)
    check = _check(validator, "art-10", quote)
    assert check.verdict == "invalid"
    assert "characters" in check.reason


def test_length_bounds_are_inclusive(validator):
    assert len(normalize_quote("a unidade consumidor")) == 20
    assert _check(validator, "art-10", "a unidade consumidor").verdict == "valid"


def test_article_cited_with_caput_quote_is_valid(validator):
    check = _check(validator, "art-10", "Art. 10. A distribuidora deve")
    assert check.verdict == "valid"


def test_article_cited_with_paragraph_quote_is_imprecise(validator):
    check = _check(validator, "art-10", "O prazo de religação de urgência é de 4 horas")
    assert check.verdict == "imprecise"
    assert check.matched_unit_id == "art-10-p1"


def test_paragraph_cited_with_inciso_quote_is_imprecise(validator):
    check = _check(validator, "art-10-p1", "na área urbana, quando houver pagamento")
    assert check.verdict == "imprecise"
    assert check.matched_unit_id == "art-10-p1-inc-I"


def test_quote_from_a_sibling_unit_is_invalid_with_a_hint(validator):
    check = _check(validator, "art-10-p1-inc-I", "a unidade consumidora em até 24 horas")
    assert check.verdict == "invalid"
    assert "'art-10'" in check.reason


def test_nfkc_folds_ordinal_indicator():
    assert normalize("§ 1º") == normalize("§ 1o")


def test_answer_without_citations_is_invalid(validator):
    validation = validator.validate(
        AnswerSchema(answer="Sim.", citations=[], abstained=False), CONTEXT
    )
    assert not validation.ok
    assert validation.errors == ["an answer that does not abstain needs at least one citation"]


def test_imprecise_citation_still_passes(validator):
    answer = AnswerSchema(
        answer="Em 4 horas.",
        citations=[Citation(unit_id="art-10", quote="prazo de religação de urgência é de 4 horas")],
        abstained=False,
    )
    validation = validator.validate(answer, CONTEXT)
    assert validation.ok
    assert [c.verdict for c in validation.checks] == ["imprecise"]


def test_one_invalid_citation_fails_the_answer(validator):
    answer = AnswerSchema(
        answer="Em 24 horas.",
        citations=[
            Citation(unit_id="art-10", quote="a unidade consumidora em até 24 horas"),
            Citation(unit_id="art-11", quote="solicitar a vistoria do medidor"),
        ],
        abstained=False,
    )
    validation = validator.validate(answer, CONTEXT)
    assert not validation.ok
    assert [c.verdict for c in validation.checks] == ["valid", "invalid"]
    assert len(validation.errors) == 1

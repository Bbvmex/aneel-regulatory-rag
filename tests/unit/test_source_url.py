import pytest

from aneel_rag.ingest.source_url import (
    build_source_url,
    encode_fragment_text,
    strip_label,
    unique_prefix,
)

BASE = "https://leis.org/x/ren-1000"

ART_23 = "Art. 23. A distribuidora deve informar ao consumidor o prazo de ligação nova."
ART_230 = "Art. 230. A distribuidora deve informar ao consumidor o valor da fatura."
PAGE = f"{ART_23}\n§ 1º O prazo conta da aprovação.\n{ART_230}\n"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Art. 23. A distribuidora deve", "A distribuidora deve"),
        ("Art. 1º Esta Resolução", "Esta Resolução"),
        ("Art. 96-A. O consumidor", "O consumidor"),
        ("§ 2º Para central geradora", "Para central geradora"),
        ("Parágrafo único. O contrato", "O contrato"),
        ("IV - agente exportador;", "agente exportador;"),
        ("I-A - autoconsumo remoto:", "autoconsumo remoto:"),
        ("I - C - armazenador autônomo:", "armazenador autônomo:"),
        ("II-Programa Casa Verde", "Programa Casa Verde"),
        ("II \u2013 central geradora;", "central geradora;"),
        ("b) unidade consumidora", "unidade consumidora"),
        ("A distribuidora deve", "A distribuidora deve"),
    ],
)
def test_strip_label(raw, expected):
    assert strip_label(raw) == expected


def test_prefix_extends_past_collision_between_art_23_and_230():
    # Both start with the same 7 words; prefix grows until they diverge.
    assert unique_prefix(ART_23, PAGE) == "A distribuidora deve informar ao consumidor o prazo"
    assert unique_prefix(ART_230, PAGE) == "A distribuidora deve informar ao consumidor o valor"


def test_short_prefix_when_already_unique():
    assert unique_prefix("§ 1º O prazo conta da aprovação.", PAGE) == "O prazo conta da aprovação."


def test_amended_unit_disambiguated_from_struck_old_version():
    # The struck old wording stays visible on the page and shares the opening words.
    shared = "Para central geradora que faça uso do mesmo ponto de conexão para consumir"
    old = f"§ 2º {shared} energia, deve ser celebrado um CUSD."
    new = f"§ 2º {shared} e injetar energia, deve ser celebrado um único CUSD."
    page = f"{old}\n{new}"
    # "consumir e" also matches inside "consumir energia" as a substring; counting it is
    # conservative (one extra word), never ambiguous.
    assert unique_prefix(new, page) == f"{shared} e injetar"
    assert unique_prefix(old, page) == f"{shared} energia,"


def test_match_is_case_and_whitespace_insensitive():
    page = "A  DISTRIBUIDORA deve\ninformar ao consumidor o prazo de ligação nova."
    assert unique_prefix(ART_23, page) is not None


def test_no_unique_prefix_returns_none():
    unit = "Art. 5º O consumidor deve pagar."
    page = f"{unit}\n{unit}"
    assert unique_prefix(unit, page) is None


def test_unit_absent_from_page_returns_none():
    assert unique_prefix("Art. 9º Texto que não está na página.", PAGE) is None


def test_revoked_unit_gets_no_url():
    assert build_source_url(BASE, ART_23, PAGE, status="revoked") is None


def test_url_format_and_encoding():
    url = build_source_url(BASE, "§ 1º O prazo conta da aprovação.", PAGE, status="active")
    assert url == f"{BASE}#:~:text=O%20prazo%20conta%20da%20aprova%C3%A7%C3%A3o."


def test_reserved_fragment_characters_are_escaped():
    assert encode_fragment_text("art. 96-A, & mais") == "art.%2096%2DA%2C%20%26%20mais"

"""Parser tests on real excerpts (tests/fixtures/html, cut by scripts/cut_fixtures.py).

Fixture names carry the inspection finding they cover (A-M, ADR-002) or the plan case.
"""

from functools import cache
from pathlib import Path

import pytest

from aneel_rag.ingest import annotations as ann
from aneel_rag.ingest.extract_law_content import extract
from aneel_rag.ingest.html_load import load_root
from aneel_rag.ingest.labels import parse_label
from aneel_rag.ingest.parser import ParseResult
from aneel_rag.ingest.pipeline import parse_root

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "html"


@cache
def parse(name: str) -> ParseResult:
    return parse_root(load_root((FIXTURES / f"{name}.html").read_bytes()))


def units(name: str) -> dict:
    return {u.id: u for u in parse(name).units}


# ---- plan cases -------------------------------------------------------------------------
def test_simple_article():
    (unit,) = parse("simple_article").units
    assert (unit.id, unit.kind, unit.status) == ("art-52", "caput", "active")
    assert unit.text.startswith("Art. 52. A distribuidora não pode cobrar")
    assert unit.source_anchor == "article52.#0"


def test_paragraphs_and_incisos():
    assert list(units("paragraphs_incisos")) == [
        "art-256",
        "art-256-pu",
        "art-256-pu-inc-I",
        "art-256-pu-inc-II",
    ]
    inc = units("paragraphs_incisos")["art-256-pu-inc-II"]
    assert inc.parent_id == "art-256-pu"
    assert inc.hierarchy_path[-3:] == ["Art. 256", "Parágrafo único", "II"]


def test_letter_article():
    (unit,) = parse("g1_single_annotated_line").units
    assert unit.id == "art-48-a"
    assert unit.label == "Art. 48-A"


# ---- A: cut of the related-norms list and download buttons -------------------------------
def test_a_extract_drops_related_norms_and_buttons():
    page = (FIXTURES / "a_full_page.html").read_bytes()
    assert b"SELECT " in page and b"Download Voto" in page
    out = extract(page, "0" * 64)
    assert "SELECT" not in out
    assert "Norma em vigor" not in out and "Norma revogada" not in out
    assert "Download" not in out
    assert 'data-summary-id="article1º"' in out
    assert "style=" not in out


def test_a_extract_is_deterministic():
    page = (FIXTURES / "a_full_page.html").read_bytes()
    assert extract(page, "0" * 64) == extract(page, "0" * 64)


def test_a_preamble_goes_to_manifest():
    result = parse_root(load_root(extract((FIXTURES / "a_full_page.html").read_bytes(), "0")))
    pre = result.preamble
    assert pre["title"].startswith("RESOLUÇÃO NORMATIVA ANEEL Nº 1.000")
    assert pre["ementa"].startswith("Estabelece as Regras de Prestação")
    assert pre["enacting_clause"].endswith("resolve :")
    assert any(n.startswith("Vide Despacho nº 1.731/2025") for n in pre["notes"])
    assert {u.article_id for u in result.units} == {"art-1"}
    assert result.units[0].hierarchy_path[:2] == [
        "TÍTULO I — PARTE GERAL",
        "CAPÍTULO I — DAS DISPOSIÇÕES GERAIS",
    ]


# ---- B: a single <br> also separates devices; unlabeled lines continue the unit ----------
def test_b_single_br_separates_alineas():
    ids = list(units("b_single_br_alineas"))
    assert ids[2:5] == ["art-221-inc-I-al-a", "art-221-inc-I-al-b", "art-221-inc-I-al-c"]


def test_b_continuation_lines_stay_in_their_unit():
    p1 = units("c_formula_and_inline_tags")["art-73-a-p1"]
    assert "\nem que:\nPg é a potência" in p1.text
    assert parse("c_formula_and_inline_tags").continuation["art-73-a"] > 0


# ---- C: labels must continue the sequence ------------------------------------------------
def test_c_formula_variable_is_not_an_inciso():
    result = parse("c_formula_and_inline_tags")
    assert "art-73-a-p1-inc-C" not in units("c_formula_and_inline_tags")
    assert "C - é o consumo" in units("c_formula_and_inline_tags")["art-73-a-p1"].text
    assert [r["label"] for r in result.rejected] == ["C -"]


def test_c_struck_labels_feed_the_sequence():
    # Old "§ 1º" (struck) then new "§ 1º": the repeat is legal only after the struck version.
    ids = list(units("g4_annotation_outside_b"))
    assert ids.count("art-160-p1") == 1
    assert "art-160-p5-inc-II" in ids and not parse("g4_annotation_outside_b").rejected


# ---- D: inciso label variants ------------------------------------------------------------
@pytest.mark.parametrize(
    "text,display",
    [
        ("II-Programa Casa Verde e Amarela", "II"),
        ("I-Contrato de Uso do Sistema", "I"),
        ("I-A - autoconsumo remoto", "I-A"),
        ("I - C - armazenador autônomo", "I-C"),
        ("II-A: até 30 de setembro de 2022", "II-A"),
        ("IV \u2013 agente exportador", "IV"),
        ("IV\u00a0- agente exportador", "IV"),
        ("I - A distribuidora deve", "I"),
    ],
)
def test_d_inciso_variants(text, display):
    label = parse_label(text)
    assert label is not None and label.kind == "inc" and label.display == display


def test_d_no_space_inciso_in_real_text():
    unit = units("d_inciso_variants")["art-480-inc-II"]
    assert unit.text.startswith("II-Programa")
    assert unit.status == "revoked"


# ---- E: span-less article accepted only as the successor --------------------------------
def test_e_article_without_span():
    result = parse("e_article_without_span")
    art35 = units("e_article_without_span")["art-35"]
    assert result.fallback_articles == ["Art. 35"]
    assert art35.status == "amended"
    assert "do responsável pela central geradora, pelo SAE autônomo" in art35.text
    assert "art-35-inc-III-al-c" in units("e_article_without_span")


# ---- F: quotations of other norms -------------------------------------------------------
def test_f_quoted_devices_do_not_become_units():
    got = units("f_quotes_other_norms")
    assert list(got) == ["art-673", "art-674", "art-675", "art-676"]
    assert got["art-673"].text.count("III - declaração emitida") == 2
    assert all(u.quotes_other_norm for u in got.values())
    assert parse("f_quotes_other_norms").quotes_without_nr == []


# ---- G: status of current text -----------------------------------------------------------
def test_g1_single_annotated_line():
    unit = units("g1_single_annotated_line")["art-48-a"]
    assert unit.status == "added"
    assert "(Redação" not in unit.text


def test_g2_annotation_only_on_the_last_line():
    got = units("g2_annotation_on_last_line")
    assert got["art-339-a"].status == "added"  # inherits the annotation of the block's last line
    assert got["art-339-a"].amended_by == got["art-339-a-pu"].amended_by


def test_g3_mixed_bold_block():
    got = units("g3_mixed_bold_block")
    assert {u.status for u in got.values()} == {"added"}
    assert all(u.amended_by[0].norma == "Resolução Normativa nº 1059/2023" for u in got.values())


def test_g4_annotation_outside_bold():
    unit = units("g4_annotation_outside_b")["art-160-p5-inc-II"]
    assert unit.status == "amended"
    assert unit.amended_by[0].norma == "Resolução Normativa nº 1081/2023"


# ---- H: superseded and revoked wording -------------------------------------------------
def test_h1_superseded_wording_with_another_label_is_dropped():
    got = units("h1_superseded_relabelled")
    assert "art-108-pu" not in got
    assert got["art-108-p1"].status == "amended"


def test_h2_whole_article_struck_old_versions():
    got = units("h2_old_versions_and_dates")
    assert sum(u.kind == "caput" for u in got.values()) == 1
    assert "SAE autônomo" in got["art-157"].text  # only the current wording survives
    assert parse("h2_old_versions_and_dates").orphans == []


def test_h3_revoked_device_keeps_text():
    unit = units("h3_revoked_device")["art-59-p2"]
    assert unit.status == "revoked"
    assert unit.text.startswith("§ 2º Para microgeração")
    assert unit.amended_by[0].kind == "revoked"
    assert unit.source_url is None


def test_h4_revocation_covers_the_struck_block():
    got = units("h4_revoked_block")
    block = [k for k in got if k.startswith("art-179-p2")]
    assert block == [f"art-179-p2{s}" for s in ("", "-inc-I", "-inc-II", "-inc-III", "-inc-IV")]
    assert {got[k].status for k in block} == {"revoked"}
    assert got["art-179-p3"].status == "active"


def test_h5_whole_article_revoked():
    (unit,) = parse("h5_whole_article_revoked").units
    assert (unit.id, unit.status) == ("art-667", "revoked")


# ---- I: validity notes ------------------------------------------------------------------
def test_i_suspensos_note_becomes_metadata():
    unit = units("i_suspensos_note")["art-323-inc-II"]
    assert unit.notes == [
        "Suspensos os efeitos referentes ao prazo de 60 (sessenta) ciclos, "
        "conforme Despacho nº 2006/2024"
    ]
    assert "Suspensos" not in unit.text
    assert unit.status == "active"


def test_i_vide_note_on_revoked_paragraph():
    assert units("h4_revoked_block")["art-179-p2"].notes == [
        "Vide afastamento do desconto, dado pelo Despacho nº 1731/2025"
    ]


# ---- J: amending act and date from the link tooltip ------------------------------------
def test_j_amended_by_has_norm_and_date():
    (first,) = units("h2_old_versions_and_dates")["art-157"].amended_by
    assert first.model_dump() == {
        "kind": "amended",
        "norma": "Resolução Normativa nº 1162/2026",
        "data": "2026-06-02",
    }


def test_j_annotation_parser():
    (a,) = ann.find(
        "(Redação dada pela Resolução Normativa nº 1.162/2026)",
        [("1.162", " Data da Norma: 02.06.2026 - Estabelecer")],
    )
    assert (a.kind, a.norma, a.data) == (
        "amended",
        "Resolução Normativa nº 1162/2026",
        "2026-06-02",
    )


# ---- K: inline noise --------------------------------------------------------------------
def test_k_inline_tags_do_not_split_words():
    p1 = units("c_formula_and_inline_tags")["art-73-a-p1"]
    assert "inciso II do caput, deve" in p1.text  # source: <em>ca<fig></fig>put,</em>


def test_k_figures_become_markers():
    p1 = units("c_formula_and_inline_tags")["art-73-a-p1"]
    assert p1.has_figure and p1.figures == ["Resnorm-1000-2021-fig1_XiOB.png"]
    assert "[FIGURA: Resnorm-1000-2021-fig1_XiOB.png]" in p1.text


def test_k_text_is_nfc_without_invisible_chars():
    import unicodedata

    for name in ("c_formula_and_inline_tags", "h4_revoked_block"):
        for unit in parse(name).units:
            assert unicodedata.is_normalized("NFC", unit.text)
            assert not any(ch in unit.text for ch in "\u200b\u00ad\ufeff")


# ---- L: footer --------------------------------------------------------------------------
def test_l_footer_is_not_a_unit():
    result = parse("l_footer_and_annex_start")
    assert result.footer[0] == "ANDRÉ PEPITONE DA NÓBREGA"
    assert result.footer[1].startswith("Este texto não substitui")
    assert all("PEPITONE" not in u.text for u in result.units)
    assert units("l_footer_and_annex_start")["art-679"].text == (
        "Art. 679. Esta Resolução entra em vigor em 3 de janeiro de 2022."
    )


# ---- M: headings -------------------------------------------------------------------------
def test_m_superseded_heading_is_dropped_and_annotation_stripped():
    result = parse("m_superseded_heading")
    assert result.superseded_headings == [
        "Seção VII — Da Arrecadação da Contribuição Para o Custeio do Serviço de Iluminação Pública"
    ]
    section = units("m_superseded_heading")["art-476"].hierarchy_path[0]
    assert section.startswith(
        "Seção VII — Da Arrecadação da Contribuição Para o Custeio, a Expansão"
    )
    assert "(Redação" not in section


# ---- annexes and tables -----------------------------------------------------------------
def test_annex_i_split_by_clause():
    got = units("l_footer_and_annex_start")
    assert list(got) == ["art-679", "annex-I-intro", "annex-I-cl-1", "annex-I-cl-2"]
    intro = got["annex-I-intro"]
    assert intro.doc_type == "annex" and intro.status == "amended"
    assert "CNPJ no (00.000.000" not in intro.text  # struck old wording dropped


def test_annex_iv_rows_repeat_the_header():
    got = parse("annex_iv_table").units
    assert len(got) == 75  # 77 rows = header + 1 struck (art. 477, §2º) + 75 current
    assert got[3].text == (
        "Tipo: 1 | Dispositivo: art. 76, § 5º | Prazo: 10 dias úteis | Descrição: "
        + got[3].text.split("Descrição: ")[1]
    )
    assert got[3].status == "added"


def test_table_inside_article_is_continuation_text():
    (unit,) = parse("table_in_article").units
    assert "Disponibilidade mensal garantida (kWh/ mês /UC) |" in unit.text
    assert "\n45 | 1.500 | 700" in unit.text


# ---- defects of the official text -------------------------------------------------------
def test_defect_doubled_label():
    p2 = units("defect_doubled_label")["art-250-p2"]
    assert p2.text.startswith("§ 2º A distribuidora pode oferecer")
    assert [g["kind"] for g in parse("defect_doubled_label").gaps] == ["doubled label"]


def test_inline_paragraphs_are_split_out_of_the_previous_one():
    # §§ 5º and 6º of Art. 485 sit on the § 4º line; the cross-references must not split.
    got = units("defect_paragraph_gap")
    assert got["art-485-p4"].text.endswith(
        "para que esta custeie e execute tais obras, ressalvado o disposto no § 6º"
    )
    assert got["art-485-p5"].text == (
        "§ 5º A notificação do § 4º deve ser realizada na apresentação da documentação disposta "
        "no caput , ou por ocasião do encaminhamento do Termo de Compromisso do § 7º"
    )
    assert got["art-485-p6"].text == (
        "§ 6º Não são de responsabilidade da distribuidora itens que não são objeto do seu "
        "contrato de concessão ou de permissão, a exemplo das instalações internas da unidade "
        "consumidora e das instalações relacionadas ao serviço público de iluminação pública ou "
        "de iluminação de vias internas."
    )
    assert [got[f"art-485-p{n}"].source_anchor for n in (4, 5, 6, 7)] == [
        f"article485.#{n}" for n in (17, 18, 19, 20)
    ]
    assert "art-485-p12" in got
    result = parse("defect_paragraph_gap")
    assert result.gaps == []
    assert [(r["from"], r["unit"]) for r in result.inline_repairs] == [
        ("art-485-p4", "art-485-p5"),
        ("art-485-p5", "art-485-p6"),
    ]


def test_defect_missing_line_break_is_split():
    got = units("defect_missing_line_break")
    assert got["art-666-p1-inc-II"].text.endswith("não enquadradas no inciso I do § 1º")
    assert got["art-666-p2"].text.startswith("§ 2º Durante a realização")
    assert "art-666-p2-inc-II" in got


def test_defect_repeated_and_missing_alinea():
    got = units("defect_repeated_and_missing_alinea")
    assert "art-668-inc-III-al-d-2" in got
    assert got["art-668-inc-III-al-g"].text.startswith("g) art. 324")
    assert not parse("defect_repeated_and_missing_alinea").rejected

"""Cut the real HTML fixtures in tests/fixtures/html from the versioned extract.

Each fixture is a contiguous run of top-level nodes of the norm, so it is real, well-formed
markup. The full-page fixture needs the unversioned data/raw/ren1000.html and is skipped
without it. Usage: uv run python scripts/cut_fixtures.py
"""

import copy
import re
from pathlib import Path

from bs4 import BeautifulSoup, Tag

ROOT = Path(__file__).resolve().parents[1]
EXTRACT = ROOT / "data" / "raw" / "ren1000_law_content.html"
FULL = ROOT / "data" / "raw" / "ren1000.html"
OUT = ROOT / "tests" / "fixtures" / "html"

# name: (start, end); a start/end is an article number ("339-A"), ("text", needle) or None (end).
FIXTURES = {
    "simple_article": ("52", "53"),
    "paragraphs_incisos": ("256", "257"),
    "b_single_br_alineas": ("221", "222"),
    "c_formula_and_inline_tags": ("73-A", "74"),
    "d_inciso_variants": ("480", "481"),
    "e_article_without_span": ("34", "36"),
    "f_quotes_other_norms": ("673", "677"),
    "g1_single_annotated_line": ("48-A", "49"),
    "g2_annotation_on_last_line": ("339-A", "340"),
    "g3_mixed_bold_block": ("655-A", "655-B"),
    "g4_annotation_outside_b": ("160", "161"),
    "h1_superseded_relabelled": ("108", "109"),
    "h2_old_versions_and_dates": ("157", "158"),
    "h3_revoked_device": ("59", "60"),
    "h4_revoked_block": ("179", "180"),
    "h5_whole_article_revoked": ("667", "668"),
    "i_suspensos_note": ("323", "324"),
    "l_footer_and_annex_start": ("679", ("text", "CLÁUSULA TERCEIRA")),
    "m_superseded_heading": (("text", "Da Arrecadação da Contribuição Para o Custeio"), "477"),
    "annex_iv_table": (("text", "PRAZOS PARA COMPENSAÇÃO"), None),
    "table_in_article": ("519", "520"),
    "defect_doubled_label": ("250", "251"),
    "defect_paragraph_gap": ("485", "486"),
    "defect_missing_line_break": ("666", "667"),
    "defect_repeated_and_missing_alinea": ("668", "669"),
}


def _article(node: Tag) -> list[str]:
    spans = [node] if node.name == "span" and "artigo" in node.get("class", []) else []
    spans += node.select("span.artigo")
    out = []
    for span in spans:
        m = re.match(r"article\s*(\d+)\s*[º°o]?\s*(?:-\s*([A-Za-z]))?", span["data-summary-id"])
        out.append(m.group(1) + (f"-{m.group(2).upper()}" if m.group(2) else ""))
    return out


def _matches(node, spec) -> bool:
    if isinstance(spec, tuple):
        return spec[1] in (node.get_text() if isinstance(node, Tag) else str(node))
    return isinstance(node, Tag) and spec in _article(node)


def cut(root: Tag, start, end) -> str:
    children = list(root.children)
    i = next(k for k, node in enumerate(children) if _matches(node, start))
    j = len(children)
    if end is not None:
        j = next(k for k in range(i + 1, len(children)) if _matches(children[k], end))
    # Bare strings must be re-escaped; str() would emit raw "<" and "&".
    return "".join(n.decode() if isinstance(n, Tag) else n.output_ready() for n in children[i:j])


def write(name: str, body: str, source: str) -> None:
    lines = [line.rstrip() for line in body.strip().splitlines()]
    text = (
        f"<!-- Real excerpt of {source}, cut by scripts/cut_fixtures.py ({name}). -->\n"
        '<div class="aneel-content">\n' + "\n".join(lines) + "\n</div>\n"
    )
    (OUT / f"{name}.html").write_bytes(text.encode("utf-8"))


def full_page_fixture() -> None:
    """Preamble, Art. 1º and the first related-norms entries, inside the real page wrapper."""
    soup = BeautifulSoup(FULL.read_bytes(), "lxml")
    content = soup.select_one("div.aneel-content")
    keep = copy.copy(content)
    keep.clear()
    for node in list(content.children):
        if isinstance(node, Tag) and node.get("data-summary-id") == "article2º":
            break
        keep.append(copy.copy(node))
    extras = copy.copy(content.select_one("#extras"))
    # Keep the two first entries that carry the leaked template SQL.
    for p in [p for p in extras.find_all("p") if "SELECT" in p.get_text()][2:]:
        p.decompose()
    for p in extras.find_all("p"):
        if "SELECT" not in p.get_text():
            p.decompose()
    keep.append(extras)
    page = f'<html><body><div id="law-content"><h2>ANEEL</h2>{keep}</div></body></html>'
    page = "\n".join(line.rstrip() for line in page.replace("<br/>", "<br/>\n").splitlines())
    (OUT / "a_full_page.html").write_bytes((page + "\n").encode("utf-8"))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    root = BeautifulSoup(EXTRACT.read_bytes(), "lxml").select_one("div.aneel-content")
    for name, (start, end) in FIXTURES.items():
        write(name, cut(root, start, end), EXTRACT.name)
    if FULL.exists():
        full_page_fixture()
    print(f"wrote {len(FIXTURES) + FULL.exists()} fixtures to {OUT}")


if __name__ == "__main__":
    main()

from pathlib import Path

from bs4 import BeautifulSoup, Tag

# Leftovers of the related-norms list; none may reach a unit.
FORBIDDEN = ("SELECT ", "Norma revogada", "Norma em vigor")


def load_root(html: str | bytes) -> Tag:
    soup = BeautifulSoup(html, "lxml")
    root = soup.select_one("div.aneel-content")
    if root is None:
        raise ValueError("div.aneel-content not found; pass the law-content extract")
    return root


def load_extract(path: Path) -> Tag:
    root = load_root(path.read_bytes())
    text = root.get_text()
    leaked = [s for s in FORBIDDEN if s in text]
    if leaked:
        raise ValueError(f"extract contains related-norms leftovers: {leaked}")
    return root


def page_text(root: Tag) -> str:
    """Visible text for deep-link uniqueness: struck text included, figure markers excluded."""
    parts = []
    for s in root.find_all(string=True):
        if s.find_parent("span", class_="figura") is None:
            parts.append(str(s))
    return "".join(parts)

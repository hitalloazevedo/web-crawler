"""
html_parser.py
--------------
Responsável por extrair hyperlinks de uma página HTML.
Isolado do crawler para facilitar testes e substituição de biblioteca de parsing.
"""

from typing import List
from bs4 import BeautifulSoup

from url_normalizer import normalize_url


def extract_links(html: str, base_url: str) -> List[str]:
    """
    Extrai e normaliza todos os hyperlinks (<a href="...">) de um HTML.

    Parâmetros:
    - html: conteúdo HTML da página
    - base_url: URL da página atual (usada para resolver links relativos)

    Retorna lista de URLs normalizadas e válidas (sem duplicatas).
    """
    soup = BeautifulSoup(html, "html.parser")
    links = []
    seen = set()

    for tag in soup.find_all("a", href=True):
        raw_href = tag["href"]
        normalized = normalize_url(raw_href, base_url)

        # Descarta inválidos e duplicatas dentro da mesma página
        if normalized and normalized not in seen:
            seen.add(normalized)
            links.append(normalized)

    return links

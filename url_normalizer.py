"""
url_normalizer.py
-----------------
Responsável por normalizar e validar URLs.
Garante consistência no grafo, evitando duplicatas por variações de formato.
"""

from urllib.parse import urlparse, urlunparse, urljoin
from typing import Optional


# Esquemas inválidos que não devem ser rastreados
INVALID_SCHEMES = {"javascript", "mailto", "tel", "ftp", "data", "void"}


def normalize_url(url: str, base_url: str = "") -> Optional[str]:
    """
    Normaliza uma URL para uma forma canônica.

    Etapas:
    - Resolve URLs relativas usando base_url
    - Remove trailing slashes da path (exceto root "/")
    - Remove fragmentos (#ancora)
    - Remove parâmetros de query (opcional: pode ser configurado)
    - Garante que apenas esquemas http/https sejam aceitos

    Retorna None se a URL for inválida ou não rastreável.
    """
    if not url:
        return None

    url = url.strip()

    # Rejeita esquemas inválidos antes de qualquer parse
    scheme_prefix = url.split(":")[0].lower()
    if scheme_prefix in INVALID_SCHEMES:
        return None

    # Resolve URL relativa usando a base
    if base_url:
        url = urljoin(base_url, url)

    try:
        parsed = urlparse(url)
    except Exception:
        return None

    # Aceita apenas http e https
    if parsed.scheme not in ("http", "https"):
        return None

    # Remove fragmentos (âncoras) — não representam páginas distintas
    # Remove query string para tratar ?page=1 e ?page=2 como a mesma página
    # Remove trailing slash; se path ficar vazio (raiz), mantém vazio
    # pois urlunparse já formata "https://example.com" corretamente sem path
    path = parsed.path.rstrip("/")

    normalized = urlunparse((
        parsed.scheme,
        parsed.netloc.lower(),  # domínio em lowercase
        path,
        "",   # params
        "",   # query  ← removido intencionalmente
        "",   # fragment ← removido intencionalmente
    ))

    return normalized


def get_domain(url: str) -> str:
    """Extrai apenas o domínio (netloc) de uma URL."""
    return urlparse(url).netloc.lower()


def is_same_domain(url: str, base_domain: str) -> bool:
    """
    Verifica se uma URL pertence ao mesmo domínio base.
    Subdomínios são tratados como domínios externos por padrão.
    """
    return get_domain(url) == base_domain

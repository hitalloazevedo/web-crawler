"""
main.py
-------
Ponto de entrada do crawler via linha de comando.

Uso:
    python main.py https://example.com
    python main.py https://example.com --max-pages 500 --max-depth 3 --output grafo.json
    python main.py https://example.com --concurrency 20 --timeout 15
"""

import argparse
import asyncio
import json
import sys
from urllib.parse import urlparse

from crawler import Crawler, CrawlerConfig
from logger import logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Website Crawler → Navigation Graph Builder",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("url", help="URL de entrada (entry point)")
    parser.add_argument("--max-pages", type=int, default=1000, help="Limite de páginas a visitar")
    parser.add_argument("--max-depth", type=int, default=5, help="Profundidade máxima de navegação")
    parser.add_argument("--timeout", type=int, default=10, help="Timeout por requisição (segundos)")
    parser.add_argument("--concurrency", type=int, default=10, help="Requisições simultâneas")
    parser.add_argument("--output", type=str, default=None, help="Caminho do arquivo JSON de saída")
    parser.add_argument(
        "--follow-subdomains", action="store_true", help="Explorar subdomínios do mesmo domínio"
    )
    parser.add_argument("--debug", action="store_true", help="Habilitar logs de debug")
    return parser.parse_args()


def default_output_path(url: str) -> str:
    """Deriva um nome de arquivo a partir do domínio da URL de entrada."""
    domain = urlparse(url).netloc or "graph"
    # Remove caracteres inválidos em nomes de arquivo
    safe = domain.replace(":", "_").replace("/", "_")
    return f"{safe}-crawl-graph.json"


async def main():
    args = parse_args()

    if args.debug:
        import logging
        logging.getLogger("crawler").setLevel(logging.DEBUG)

    config = CrawlerConfig(
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        timeout_seconds=args.timeout,
        max_concurrent=args.concurrency,
        follow_subdomains=args.follow_subdomains,
    )

    try:
        crawler = Crawler(args.url, config)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    graph = await crawler.run()

    # Determina o caminho de saída: argumento --output ou nome derivado do domínio
    output_path = args.output or default_output_path(args.url)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2, ensure_ascii=False)

    logger.info(f"Grafo salvo em: {output_path}")
    logger.info(f"Total de nós: {len(graph)}")
    logger.info(f"Total de arestas: {sum(len(v) for v in graph.values())}")


if __name__ == "__main__":
    asyncio.run(main())
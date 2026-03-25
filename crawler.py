"""
crawler.py
----------
Motor principal do crawler assíncrono.

Justificativa da escolha de Python + asyncio:
- asyncio com aiohttp permite centenas de requisições HTTP concorrentes
  sem criar threads (I/O-bound problem → perfeito para async)
- BeautifulSoup é a biblioteca de HTML parsing mais madura do ecossistema Python
- A stdlib (collections.deque, urllib.parse) cobre BFS e normalização de URLs
- Tipagem estática via type hints melhora manutenibilidade

Arquitetura:
    Crawler              ← orquestração BFS + concorrência
    ├── html_parser      ← extração de links do HTML
    ├── url_normalizer   ← normalização e validação de URLs
    ├── graph_builder    ← construção e exportação do grafo
    └── logger           ← progresso e estatísticas
"""

import asyncio
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

import aiohttp

from graph_builder import GraphBuilder
from html_parser import extract_links
from logger import CrawlStats, logger
from url_normalizer import get_domain, is_same_domain, normalize_url


@dataclass
class CrawlerConfig:
    """Configurações do crawler com valores padrão seguros."""
    max_pages: int = 1000          # Limite total de páginas a visitar
    max_depth: int = 5             # Profundidade máxima a partir da entry URL
    timeout_seconds: int = 10      # Timeout por requisição HTTP
    max_concurrent: int = 10       # Requisições simultâneas (semáforo)
    user_agent: str = "WebCrawler/1.0 (+https://github.com/crawler)"
    follow_subdomains: bool = False  # Se True, subdomínios do mesmo domínio são explorados


class Crawler:
    """
    Crawler BFS assíncrono que constrói um grafo de navegação.

    Uso:
        crawler = Crawler("https://example.com", config)
        graph = await crawler.run()
    """

    def __init__(self, entry_url: str, config: Optional[CrawlerConfig] = None):
        self.entry_url = normalize_url(entry_url)
        if not self.entry_url:
            raise ValueError(f"URL de entrada inválida: {entry_url}")

        self.config = config or CrawlerConfig()
        self.base_domain = get_domain(self.entry_url)

        self.graph = GraphBuilder()
        self.stats = CrawlStats()

        # Conjunto de URLs já visitadas (controle de loop)
        self._visited: Set[str] = set()

    # ------------------------------------------------------------------
    # Ponto de entrada público
    # ------------------------------------------------------------------

    async def run(self) -> Dict[str, List[str]]:
        """
        Executa o crawl completo e retorna o grafo como dicionário.
        """
        logger.info(f"Iniciando crawl: {self.entry_url}")
        logger.info(f"Domínio base: {self.base_domain}")
        logger.info(
            f"Limites: max_pages={self.config.max_pages}, "
            f"max_depth={self.config.max_depth}, "
            f"concorrência={self.config.max_concurrent}"
        )

        # Semáforo para limitar requisições simultâneas
        semaphore = asyncio.Semaphore(self.config.max_concurrent)

        connector = aiohttp.TCPConnector(limit=self.config.max_concurrent)
        timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        headers = {"User-Agent": self.config.user_agent}

        async with aiohttp.ClientSession(
            connector=connector, timeout=timeout, headers=headers
        ) as session:
            await self._bfs(session, semaphore)

        logger.info(self.stats.report())
        logger.info(
            f"Grafo final: {self.graph.node_count} nós, {self.graph.edge_count} arestas"
        )
        return self.graph.to_dict()

    # ------------------------------------------------------------------
    # BFS com processamento em lotes concorrentes
    # ------------------------------------------------------------------

    async def _bfs(self, session: aiohttp.ClientSession, semaphore: asyncio.Semaphore):
        """
        Percorre o site em largura (BFS).

        Cada nível da BFS é processado em paralelo (lote de tarefas async).
        Isso mantém a semântica de profundidade enquanto aproveita concorrência.
        """
        # Fila de (url, profundidade_atual)
        queue: deque = deque()
        queue.append((self.entry_url, 0))
        self._visited.add(self.entry_url)

        while queue:
            # Extrai todas as URLs do nível atual para processamento em lote
            current_level = []
            current_depth = queue[0][1]  # profundidade do primeiro item

            while queue and queue[0][1] == current_depth:
                current_level.append(queue.popleft())

            if current_depth > self.config.max_depth:
                logger.info(f"Profundidade máxima ({self.config.max_depth}) atingida.")
                break

            logger.info(
                f"[Profundidade {current_depth}] Processando {len(current_level)} URL(s) | "
                f"Visitadas: {self.stats.pages_visited}/{self.config.max_pages}"
            )

            # Cria tarefas async para todo o lote e aguarda
            tasks = [
                self._fetch_and_process(session, semaphore, url, depth)
                for url, depth in current_level
                if self.stats.pages_visited < self.config.max_pages
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Enfileira URLs descobertas para o próximo nível
            for result in results:
                if isinstance(result, list):
                    for child_url in result:
                        if (
                            child_url not in self._visited
                            and self.stats.pages_visited < self.config.max_pages
                            and is_same_domain(child_url, self.base_domain)
                        ):
                            self._visited.add(child_url)
                            self.stats.urls_queued += 1
                            queue.append((child_url, current_depth + 1))

            if self.stats.pages_visited >= self.config.max_pages:
                logger.warning(
                    f"Limite de páginas ({self.config.max_pages}) atingido. Encerrando."
                )
                break

    # ------------------------------------------------------------------
    # Fetch + parse + atualização do grafo por URL
    # ------------------------------------------------------------------

    async def _fetch_and_process(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        url: str,
        depth: int,
    ) -> List[str]:
        """
        Baixa uma página, extrai links e atualiza o grafo.

        Retorna lista de URLs internas descobertas (para enfileirar na BFS).
        Retorna lista vazia em caso de erro.
        """
        async with semaphore:  # respeita o limite de concorrência
            html = await self._fetch(session, url)

        if html is None:
            # Erro já logado em _fetch; nó sem arestas permanece no grafo
            self.graph.add_node(url)
            return []

        self.stats.pages_visited += 1

        # Extrai links da página
        all_links = extract_links(html, url)

        # Separa links internos (para explorar) de externos (apenas nó no grafo)
        internal_links = []
        external_links = []

        for link in all_links:
            if is_same_domain(link, self.base_domain):
                internal_links.append(link)
            else:
                external_links.append(link)
                self.stats.pages_skipped_external += 1

        # Registra todas as arestas no grafo (internas + externas)
        self.graph.add_edges(url, internal_links + external_links)

        logger.debug(
            f"[{depth}] {url} → {len(internal_links)} internos, {len(external_links)} externos"
        )

        # Retorna apenas internos para a BFS continuar
        return internal_links

    # ------------------------------------------------------------------
    # Requisição HTTP com tratamento de erros
    # ------------------------------------------------------------------

    async def _fetch(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """
        Realiza GET na URL e retorna o HTML como string.

        Retorna None se:
        - Status HTTP >= 400
        - Timeout
        - Exceção de rede
        - Content-Type não é HTML
        """
        try:
            async with session.get(url, allow_redirects=True) as response:
                # Ignora erros HTTP
                if response.status >= 400:
                    logger.warning(f"HTTP {response.status}: {url}")
                    self.stats.pages_skipped_error += 1
                    self.stats.errors.append(f"HTTP {response.status}: {url}")
                    return None

                # Ignora respostas não-HTML (PDFs, imagens, etc.)
                content_type = response.headers.get("Content-Type", "")
                if "text/html" not in content_type:
                    logger.debug(f"Content-Type ignorado ({content_type}): {url}")
                    return None

                return await response.text(errors="replace")

        except asyncio.TimeoutError:
            logger.warning(f"Timeout: {url}")
            self.stats.errors.append(f"Timeout: {url}")
            return None

        except aiohttp.ClientError as e:
            logger.warning(f"Erro de rede em {url}: {e}")
            self.stats.errors.append(f"Erro rede: {url}")
            return None

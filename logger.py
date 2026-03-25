"""
logger.py
---------
Logging de progresso e coleta de estatísticas do crawler.
Desacoplado do crawler principal para facilitar customização de output.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import List


# Configuração do logger padrão (stdout com timestamp)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger("crawler")


@dataclass
class CrawlStats:
    """Acumula métricas durante o crawling."""
    start_time: float = field(default_factory=time.time)
    pages_visited: int = 0
    pages_skipped_error: int = 0
    pages_skipped_external: int = 0
    urls_queued: int = 0
    errors: List[str] = field(default_factory=list)

    def elapsed(self) -> float:
        return time.time() - self.start_time

    def report(self) -> str:
        return (
            f"\n{'='*50}\n"
            f"  RELATÓRIO FINAL DO CRAWL\n"
            f"{'='*50}\n"
            f"  Tempo total:          {self.elapsed():.2f}s\n"
            f"  Páginas visitadas:    {self.pages_visited}\n"
            f"  Erros HTTP (skip):    {self.pages_skipped_error}\n"
            f"  URLs externas (skip): {self.pages_skipped_external}\n"
            f"  Total URLs na fila:   {self.urls_queued}\n"
            f"{'='*50}"
        )

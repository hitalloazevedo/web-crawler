"""
graph_builder.py
----------------
Responsável por manter e exportar o grafo de navegação.

Estrutura do grafo:
    { "url_origem": ["url_destino_1", "url_destino_2"], ... }

Cada nó é uma URL única; cada aresta, um hyperlink descoberto.
URLs externas aparecem como nós sem arestas de saída (folhas do grafo).
"""

from typing import Dict, List
import json


class GraphBuilder:
    """
    Gerencia o grafo dirigido de URLs.

    - add_node: registra uma URL sem arestas (útil para URLs externas)
    - add_edges: registra os links de saída de uma página
    - to_dict: exporta o grafo como dicionário Python
    - to_json: exporta o grafo como string JSON
    """

    def __init__(self):
        # Adjacência: url -> lista de urls apontadas por ela
        self._graph: Dict[str, List[str]] = {}

    def add_node(self, url: str) -> None:
        """Garante que a URL exista no grafo, mesmo sem arestas."""
        if url not in self._graph:
            self._graph[url] = []

    def add_edges(self, source_url: str, target_urls: List[str]) -> None:
        """
        Registra arestas saindo de source_url para cada url em target_urls.
        Também garante que cada URL de destino exista como nó.
        """
        self.add_node(source_url)
        for target in target_urls:
            self.add_node(target)
            # Evita arestas duplicadas na mesma fonte
            if target not in self._graph[source_url]:
                self._graph[source_url].append(target)

    def to_dict(self) -> Dict[str, List[str]]:
        """Retorna o grafo como dicionário Python."""
        return dict(self._graph)

    def to_json(self, indent: int = 2) -> str:
        """Serializa o grafo para JSON."""
        return json.dumps(self._graph, indent=indent, ensure_ascii=False)

    @property
    def node_count(self) -> int:
        return len(self._graph)

    @property
    def edge_count(self) -> int:
        return sum(len(v) for v in self._graph.values())

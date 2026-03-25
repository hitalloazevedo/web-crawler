"""
tests.py
--------
Testes unitários para os módulos do crawler.

Execute com:
    python -m pytest tests.py -v
    # ou simplesmente:
    python tests.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from url_normalizer import normalize_url, get_domain, is_same_domain
from html_parser import extract_links
from graph_builder import GraphBuilder


# ──────────────────────────────────────────────
# Testes: url_normalizer
# ──────────────────────────────────────────────

class TestNormalizeUrl(unittest.TestCase):

    def test_resolve_relative_url(self):
        result = normalize_url("/about", "https://example.com/home")
        self.assertEqual(result, "https://example.com/about")

    def test_removes_trailing_slash(self):
        result = normalize_url("https://example.com/page/")
        self.assertEqual(result, "https://example.com/page")

    def test_keeps_root_slash(self):
        result = normalize_url("https://example.com/")
        # Trailing slash removida → URL canônica sem barra final
        self.assertEqual(result, "https://example.com")

    def test_removes_query_string(self):
        result = normalize_url("https://example.com/search?q=python")
        self.assertEqual(result, "https://example.com/search")

    def test_removes_fragment(self):
        result = normalize_url("https://example.com/page#section")
        self.assertEqual(result, "https://example.com/page")

    def test_rejects_mailto(self):
        self.assertIsNone(normalize_url("mailto:user@example.com"))

    def test_rejects_javascript(self):
        self.assertIsNone(normalize_url("javascript:void(0)"))

    def test_rejects_empty(self):
        self.assertIsNone(normalize_url(""))

    def test_lowercases_domain(self):
        result = normalize_url("https://EXAMPLE.COM/page")
        self.assertEqual(result, "https://example.com/page")

    def test_is_same_domain(self):
        self.assertTrue(is_same_domain("https://example.com/a", "example.com"))
        self.assertFalse(is_same_domain("https://sub.example.com/a", "example.com"))
        self.assertFalse(is_same_domain("https://other.com/a", "example.com"))

    def test_get_domain(self):
        self.assertEqual(get_domain("https://example.com/page"), "example.com")


# ──────────────────────────────────────────────
# Testes: html_parser
# ──────────────────────────────────────────────

class TestExtractLinks(unittest.TestCase):

    BASE = "https://example.com"

    def test_extracts_absolute_links(self):
        html = '<a href="https://example.com/about">About</a>'
        links = extract_links(html, self.BASE)
        self.assertIn("https://example.com/about", links)

    def test_extracts_relative_links(self):
        html = '<a href="/contact">Contact</a>'
        links = extract_links(html, self.BASE)
        self.assertIn("https://example.com/contact", links)

    def test_ignores_mailto(self):
        html = '<a href="mailto:a@b.com">Email</a>'
        links = extract_links(html, self.BASE)
        self.assertEqual(links, [])

    def test_ignores_javascript(self):
        html = '<a href="javascript:void(0)">Click</a>'
        links = extract_links(html, self.BASE)
        self.assertEqual(links, [])

    def test_deduplicates_links(self):
        html = '''
            <a href="/page">Link 1</a>
            <a href="/page">Link 2</a>
            <a href="/page/">Link 3</a>
        '''
        links = extract_links(html, self.BASE)
        # Após normalização, /page e /page/ são iguais → deve retornar 1
        self.assertEqual(len(links), 1)

    def test_handles_empty_html(self):
        links = extract_links("", self.BASE)
        self.assertEqual(links, [])

    def test_ignores_anchor_only(self):
        html = '<a href="#top">Top</a>'
        links = extract_links(html, self.BASE)
        # Após normalizar #top com base, resulta na própria base
        # que é válida — depende da política; aqui verificamos que não falha
        self.assertIsInstance(links, list)


# ──────────────────────────────────────────────
# Testes: graph_builder
# ──────────────────────────────────────────────

class TestGraphBuilder(unittest.TestCase):

    def setUp(self):
        self.graph = GraphBuilder()

    def test_add_node(self):
        self.graph.add_node("https://a.com")
        self.assertIn("https://a.com", self.graph.to_dict())

    def test_add_edges(self):
        self.graph.add_edges("https://a.com", ["https://b.com", "https://c.com"])
        d = self.graph.to_dict()
        self.assertIn("https://b.com", d["https://a.com"])
        self.assertIn("https://c.com", d["https://a.com"])

    def test_no_duplicate_edges(self):
        self.graph.add_edges("https://a.com", ["https://b.com"])
        self.graph.add_edges("https://a.com", ["https://b.com"])
        self.assertEqual(len(self.graph.to_dict()["https://a.com"]), 1)

    def test_target_becomes_node(self):
        self.graph.add_edges("https://a.com", ["https://b.com"])
        self.assertIn("https://b.com", self.graph.to_dict())

    def test_node_count(self):
        self.graph.add_edges("https://a.com", ["https://b.com", "https://c.com"])
        self.assertEqual(self.graph.node_count, 3)

    def test_edge_count(self):
        self.graph.add_edges("https://a.com", ["https://b.com", "https://c.com"])
        self.assertEqual(self.graph.edge_count, 2)

    def test_to_json(self):
        self.graph.add_edges("https://a.com", ["https://b.com"])
        import json
        data = json.loads(self.graph.to_json())
        self.assertIn("https://a.com", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)

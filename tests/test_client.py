"""Unit tests for the Scopus HTTP client helpers."""
from __future__ import annotations

import pytest

from scopus_mcp.config import Config
from scopus_mcp.scopus.client import parse_citation_count, ScopusClient


class TestParseCitationCount:
    """parse_citation_count must handle every format the Scopus API can return."""

    def test_plain_string(self):
        assert parse_citation_count("42") == 42

    def test_plain_integer(self):
        assert parse_citation_count(100) == 100

    def test_float_truncated(self):
        assert parse_citation_count(3.9) == 3

    def test_list_of_dicts_dollar_key(self):
        # Abstract retrieval endpoints return [{"$": "N"}]
        assert parse_citation_count([{"$": "50000"}]) == 50000

    def test_list_of_dicts_empty_dollar(self):
        assert parse_citation_count([{"$": "0"}]) == 0

    def test_empty_list(self):
        assert parse_citation_count([]) == 0

    def test_none(self):
        assert parse_citation_count(None) == 0

    def test_non_numeric_string(self):
        assert parse_citation_count("N/A") == 0

    def test_empty_string(self):
        assert parse_citation_count("") == 0

    def test_list_with_plain_string(self):
        # Some endpoints nest the string directly in the list
        assert parse_citation_count(["99"]) == 99

    def test_nested_list_of_dicts_missing_dollar(self):
        assert parse_citation_count([{"other": "42"}]) == 0

    def test_zero_string(self):
        assert parse_citation_count("0") == 0


class TestScopusClientHeaders:
    """ScopusClient must attach entitlement headers only when configured."""

    def test_insttoken_header_added_when_configured(self):
        client = ScopusClient(Config(api_key="k", inst_token="tok"))
        assert client._base_headers["X-ELS-Insttoken"] == "tok"

    def test_insttoken_header_absent_when_not_configured(self):
        client = ScopusClient(Config(api_key="k"))
        assert "X-ELS-Insttoken" not in client._base_headers

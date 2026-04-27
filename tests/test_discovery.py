"""Tests for Story 1 — Literature Discovery: explore_topic and advanced_search."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from scopus_mcp.tools.discovery import _search_topic, register_discovery_tools
from tests.conftest import MockMCP, SEARCH_ENTRY, SEARCH_RESPONSE, EMPTY_SEARCH_RESPONSE


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.request_json.return_value = (SEARCH_RESPONSE, MagicMock())
    return client


@pytest.fixture
def tools_and_client():
    mcp = MockMCP()
    client = MagicMock()
    client.request_json.return_value = (SEARCH_RESPONSE, MagicMock())
    register_discovery_tools(mcp, lambda: client)
    return mcp.tools, client


# ---------------------------------------------------------------------------
# _search_topic (internal helper, directly testable)
# ---------------------------------------------------------------------------

class TestSearchTopic:
    def test_returns_results(self, mock_client):
        result = _search_topic(mock_client, "cyber deception")
        assert result["topic"] == "cyber deception"
        assert result["total_results"] == 1826
        assert len(result["results"]) == 1
        assert result["results"][0]["title"] == "Cyber Deception: State of the Art"

    def test_query_contains_topic_and_year_filter(self, mock_client):
        _search_topic(mock_client, "cyber deception", years_back=5)
        params = mock_client.request_json.call_args[1]["params"]
        assert "TITLE-ABS-KEY(cyber deception)" in params["query"]
        assert "PUBYEAR" in params["query"]

    def test_sort_by_citations_sends_sort_param(self, mock_client):
        _search_topic(mock_client, "test", sort_by="cited_by_count")
        params = mock_client.request_json.call_args[1]["params"]
        assert params.get("sort") == "citedby-count"

    def test_sort_by_date_sends_sort_param(self, mock_client):
        _search_topic(mock_client, "test", sort_by="date")
        params = mock_client.request_json.call_args[1]["params"]
        assert params.get("sort") == "pubyear"

    def test_sort_by_relevance_omits_sort_param(self, mock_client):
        _search_topic(mock_client, "test", sort_by="relevance")
        params = mock_client.request_json.call_args[1]["params"]
        assert "sort" not in params

    def test_limit_caps_results(self, mock_client):
        many = [SEARCH_ENTRY] * 20
        mock_client.request_json.return_value = (
            {"search-results": {"opensearch:totalResults": "100", "entry": many}},
            MagicMock(),
        )
        result = _search_topic(mock_client, "test", limit=5)
        assert len(result["results"]) == 5

    def test_none_response_returns_empty(self, mock_client):
        mock_client.request_json.return_value = (None, MagicMock())
        result = _search_topic(mock_client, "test")
        assert result["results"] == []
        assert result["total_results"] == 0

    def test_from_year_derived_from_years_back(self, mock_client):
        import datetime
        result = _search_topic(mock_client, "test", years_back=3)
        expected_from_year = datetime.date.today().year - 3
        assert result["from_year"] == expected_from_year


# ---------------------------------------------------------------------------
# explore_topic (registered MCP tool)
# ---------------------------------------------------------------------------

class TestExploreTopic:
    def test_happy_path(self, tools_and_client):
        tools, client = tools_and_client
        result = tools["explore_topic"](topic="cyber deception", years_back=10, limit=20)
        assert result["topic"] == "cyber deception"
        assert "results" in result

    def test_api_error_returns_error_dict(self, tools_and_client):
        tools, client = tools_and_client
        from scopus_mcp.scopus.client import ScopusApiError
        client.request_json.side_effect = ScopusApiError("Quota exceeded", 429)
        result = tools["explore_topic"](topic="test")
        assert "error" in result
        assert result["results"] == []


# ---------------------------------------------------------------------------
# advanced_search (registered MCP tool)
# ---------------------------------------------------------------------------

class TestAdvancedSearch:
    def test_title_query(self, tools_and_client):
        tools, client = tools_and_client
        tools["advanced_search"](title="attention mechanism")
        params = client.request_json.call_args[1]["params"]
        assert "TITLE(attention mechanism)" in params["query"]

    def test_author_query(self, tools_and_client):
        tools, client = tools_and_client
        tools["advanced_search"](author="Hinton")
        params = client.request_json.call_args[1]["params"]
        assert "AUTH(Hinton)" in params["query"]

    def test_keywords_query(self, tools_and_client):
        tools, client = tools_and_client
        tools["advanced_search"](keywords="honeypot deception")
        params = client.request_json.call_args[1]["params"]
        assert "TITLE-ABS-KEY(honeypot deception)" in params["query"]

    def test_affiliation_query(self, tools_and_client):
        tools, client = tools_and_client
        tools["advanced_search"](affiliation="MIT")
        params = client.request_json.call_args[1]["params"]
        assert "AFFIL(MIT)" in params["query"]

    def test_combined_query_joins_with_and(self, tools_and_client):
        tools, client = tools_and_client
        tools["advanced_search"](title="deception", author="Smith", keywords="honeypot")
        params = client.request_json.call_args[1]["params"]
        query = params["query"]
        assert "TITLE(deception)" in query
        assert "AUTH(Smith)" in query
        assert "TITLE-ABS-KEY(honeypot)" in query
        assert " AND " in query

    def test_exact_year_filter(self, tools_and_client):
        tools, client = tools_and_client
        tools["advanced_search"](keywords="test", year="2023")
        params = client.request_json.call_args[1]["params"]
        assert "PUBYEAR = 2023" in params["query"]

    def test_year_range_filter(self, tools_and_client):
        tools, client = tools_and_client
        tools["advanced_search"](keywords="test", year="2020-2024")
        params = client.request_json.call_args[1]["params"]
        assert "PUBYEAR >= 2020" in params["query"]
        assert "PUBYEAR <= 2024" in params["query"]

    def test_doc_type_filter(self, tools_and_client):
        tools, client = tools_and_client
        tools["advanced_search"](keywords="test", doc_type="re")
        params = client.request_json.call_args[1]["params"]
        assert "DOCTYPE(re)" in params["query"]

    def test_no_criteria_returns_error(self, tools_and_client):
        tools, _ = tools_and_client
        result = tools["advanced_search"]()
        assert "error" in result
        assert result["results"] == []

    def test_none_response_returns_empty(self, tools_and_client):
        tools, client = tools_and_client
        client.request_json.return_value = (None, MagicMock())
        result = tools["advanced_search"](keywords="test")
        assert result["results"] == []
        assert result["total_results"] == 0

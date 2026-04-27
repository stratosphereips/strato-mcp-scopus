"""Tests for Story 2 — Author Discovery: find_experts_in, search_author, get_author_profile, compare_authors."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from scopus_mcp.scopus.client import ScopusApiError
from scopus_mcp.tools.authors import register_author_tools
from tests.conftest import (
    MockMCP,
    AUTHOR_PROFILE_RESPONSE,
    AUTHOR_SEARCH_RESPONSE,
    SEARCH_ENTRY,
    SEARCH_RESPONSE,
)


@pytest.fixture
def setup():
    mcp = MockMCP()
    client = MagicMock()
    register_author_tools(mcp, lambda: client)
    return mcp.tools, client


def _entry_with_author(name: str, auid: str, citations: str = "10") -> dict:
    """Build a search entry carrying a single authoreference."""
    return {
        **SEARCH_ENTRY,
        "citedby-count": citations,
        "authoreference": [
            {
                "ce:indexed-name": name,
                "@auid": auid,
                "affiliation": [{"affiliation-name": {"#text": "Test University"}}],
            }
        ],
    }


# ---------------------------------------------------------------------------
# find_experts_in
# ---------------------------------------------------------------------------

class TestFindExpertsIn:
    def test_returns_topic_in_result(self, setup):
        tools, client = setup
        client.request_json.return_value = (SEARCH_RESPONSE, MagicMock())
        result = tools["find_experts_in"]("cyber deception")
        assert result["topic"] == "cyber deception"

    def test_topic_included_in_query(self, setup):
        tools, client = setup
        client.request_json.return_value = (SEARCH_RESPONSE, MagicMock())
        tools["find_experts_in"]("cyber deception")
        params = client.request_json.call_args[1]["params"]
        assert "TITLE-ABS-KEY(cyber deception)" in params["query"]

    def test_field_adds_subjarea_filter(self, setup):
        tools, client = setup
        client.request_json.return_value = (SEARCH_RESPONSE, MagicMock())
        tools["find_experts_in"]("machine learning", field="COMP")
        params = client.request_json.call_args[1]["params"]
        assert "SUBJAREA(COMP)" in params["query"]

    def test_no_field_omits_subjarea(self, setup):
        tools, client = setup
        client.request_json.return_value = (SEARCH_RESPONSE, MagicMock())
        tools["find_experts_in"]("test")
        params = client.request_json.call_args[1]["params"]
        assert "SUBJAREA" not in params["query"]

    def test_extracts_author_from_authoreference(self, setup):
        tools, client = setup
        response = {
            "search-results": {
                "opensearch:totalResults": "1",
                "entry": [_entry_with_author("Smith J.", "auth-001")],
            }
        }
        client.request_json.return_value = (response, MagicMock())
        result = tools["find_experts_in"]("test")
        assert any(e["name"] == "Smith J." for e in result["experts"])

    def test_aggregates_paper_count_for_same_author(self, setup):
        tools, client = setup
        entry = _entry_with_author("Smith J.", "auth-001", citations="10")
        response = {
            "search-results": {
                "opensearch:totalResults": "2",
                "entry": [entry, entry],
            }
        }
        client.request_json.return_value = (response, MagicMock())
        result = tools["find_experts_in"]("test")
        smith = next(e for e in result["experts"] if e["name"] == "Smith J.")
        assert smith["paper_count"] == 2

    def test_aggregates_total_citations_from_string_citedby_count(self, setup):
        """citedby-count in search results is a plain string, not a list of dicts."""
        tools, client = setup
        entry = _entry_with_author("Smith J.", "auth-001", citations="42")
        response = {
            "search-results": {
                "opensearch:totalResults": "2",
                "entry": [entry, entry],
            }
        }
        client.request_json.return_value = (response, MagicMock())
        result = tools["find_experts_in"]("test")
        smith = next(e for e in result["experts"] if e["name"] == "Smith J.")
        # Two papers × 42 citations each = 84 total
        assert smith["total_citations"] == 84

    def test_limit_caps_expert_count(self, setup):
        tools, client = setup
        entries = [_entry_with_author(f"Author{i}", f"auth-{i:03}") for i in range(10)]
        response = {"search-results": {"opensearch:totalResults": "10", "entry": entries}}
        client.request_json.return_value = (response, MagicMock())
        result = tools["find_experts_in"]("test", limit=3)
        assert len(result["experts"]) <= 3

    def test_none_response_returns_empty(self, setup):
        tools, client = setup
        client.request_json.return_value = (None, MagicMock())
        result = tools["find_experts_in"]("test")
        assert result["experts"] == []

    def test_api_error_returns_error_dict(self, setup):
        tools, client = setup
        client.request_json.side_effect = ScopusApiError("Rate limit", 429)
        result = tools["find_experts_in"]("test")
        assert "error" in result
        assert result["experts"] == []


# ---------------------------------------------------------------------------
# search_author
# ---------------------------------------------------------------------------

class TestSearchAuthor:
    def test_builds_authname_query(self, setup):
        tools, client = setup
        client.request_json.return_value = (AUTHOR_SEARCH_RESPONSE, MagicMock())
        tools["search_author"]("Hinton")
        params = client.request_json.call_args[1]["params"]
        assert "AUTHNAME(Hinton)" in params["query"]

    def test_adds_affil_when_given(self, setup):
        tools, client = setup
        client.request_json.return_value = (AUTHOR_SEARCH_RESPONSE, MagicMock())
        tools["search_author"]("Smith", affiliation="MIT")
        params = client.request_json.call_args[1]["params"]
        assert "AFFIL(MIT)" in params["query"]

    def test_no_affil_omits_affil_clause(self, setup):
        tools, client = setup
        client.request_json.return_value = (AUTHOR_SEARCH_RESPONSE, MagicMock())
        tools["search_author"]("Hinton")
        params = client.request_json.call_args[1]["params"]
        assert "AFFIL" not in params["query"]

    def test_uses_author_search_endpoint(self, setup):
        tools, client = setup
        client.request_json.return_value = (AUTHOR_SEARCH_RESPONSE, MagicMock())
        tools["search_author"]("Hinton")
        path = client.request_json.call_args[0][1]
        assert path == "/content/search/author"

    def test_returns_summarized_authors(self, setup):
        tools, client = setup
        client.request_json.return_value = (AUTHOR_SEARCH_RESPONSE, MagicMock())
        result = tools["search_author"]("Hinton")
        assert result["total_results"] == 1
        assert result["results"][0]["name"] == "Geoffrey Hinton"

    def test_none_response_returns_empty(self, setup):
        tools, client = setup
        client.request_json.return_value = (None, MagicMock())
        result = tools["search_author"]("Unknown")
        assert result["results"] == []

    def test_api_error_returns_error_dict(self, setup):
        tools, client = setup
        client.request_json.side_effect = ScopusApiError("Server error", 500)
        result = tools["search_author"]("test")
        assert "error" in result


# ---------------------------------------------------------------------------
# get_author_profile
# ---------------------------------------------------------------------------

class TestGetAuthorProfile:
    def test_returns_name_and_metrics(self, setup):
        tools, client = setup
        client.request_json.return_value = (AUTHOR_PROFILE_RESPONSE, MagicMock())
        result = tools["get_author_profile"]("35590507000")
        assert result["name"] == "Geoffrey Hinton"
        assert result["h_index"] == 120
        assert result["document_count"] == 250

    def test_uses_correct_path_with_author_id(self, setup):
        tools, client = setup
        client.request_json.return_value = (AUTHOR_PROFILE_RESPONSE, MagicMock())
        tools["get_author_profile"]("35590507000")
        path = client.request_json.call_args[0][1]
        assert path == "/content/author/author_id/35590507000"

    def test_requests_complete_view(self, setup):
        tools, client = setup
        client.request_json.return_value = (AUTHOR_PROFILE_RESPONSE, MagicMock())
        tools["get_author_profile"]("35590507000")
        params = client.request_json.call_args[1]["params"]
        assert params.get("view") == "COMPLETE"

    def test_none_response_returns_error(self, setup):
        tools, client = setup
        client.request_json.return_value = (None, MagicMock())
        result = tools["get_author_profile"]("bad-id")
        assert "error" in result

    def test_api_error_returns_error_dict(self, setup):
        tools, client = setup
        client.request_json.side_effect = ScopusApiError("Not found", 404)
        result = tools["get_author_profile"]("bad-id")
        assert "error" in result

    def test_include_publications_false_by_default(self, setup):
        tools, client = setup
        client.request_json.return_value = (AUTHOR_PROFILE_RESPONSE, MagicMock())
        result = tools["get_author_profile"]("35590507000")
        assert "recent_publications" not in result


# ---------------------------------------------------------------------------
# compare_authors
# ---------------------------------------------------------------------------

class TestCompareAuthors:
    def test_all_successful(self, setup):
        tools, client = setup
        client.request_json.return_value = (AUTHOR_PROFILE_RESPONSE, MagicMock())
        result = tools["compare_authors"](["id1", "id2"])
        assert result["successful_count"] == 2
        assert result["failed_count"] == 0
        assert len(result["authors"]) == 2

    def test_partial_failure_tracked(self, setup):
        tools, client = setup
        client.request_json.side_effect = [
            (AUTHOR_PROFILE_RESPONSE, MagicMock()),
            (None, MagicMock()),
        ]
        result = tools["compare_authors"](["id1", "id2"])
        assert result["successful_count"] == 1
        assert result["failed_count"] == 1

    def test_result_contains_author_ids(self, setup):
        tools, client = setup
        client.request_json.return_value = (AUTHOR_PROFILE_RESPONSE, MagicMock())
        result = tools["compare_authors"](["id1", "id2"])
        assert result["author_ids"] == ["id1", "id2"]

    def test_all_failed(self, setup):
        tools, client = setup
        client.request_json.side_effect = ScopusApiError("Unavailable", 503)
        result = tools["compare_authors"](["id1", "id2"])
        assert result["successful_count"] == 0
        assert result["failed_count"] == 2

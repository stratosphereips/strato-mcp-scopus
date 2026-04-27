"""Tests for Story 3 — Citation Tracking: get_citation_network, get_citation_metrics."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from scopus_mcp.scopus.client import ScopusApiError
from scopus_mcp.tools.citations import register_citation_tools
from tests.conftest import MockMCP, ABSTRACT_RETRIEVAL_RESPONSE, SEARCH_ENTRY


# Abstract-retrieval body — the inner dict that tools receive after unwrapping.
ABS_DOC = ABSTRACT_RETRIEVAL_RESPONSE["abstracts-retrieval-response"]

# Minimal abstract body with no citingarticles link.
ABS_NO_CITING_LINK = {
    "coredata": {
        "citation-count": [{"$": "5"}],
        "link": [{"@rel": "self", "@href": "https://api.elsevier.com/..."}],
    },
    "eid": "2-s2.0-test",
}


@pytest.fixture
def setup():
    mcp = MockMCP()
    client = MagicMock()
    register_citation_tools(mcp, lambda: client)
    return mcp.tools, client


# ---------------------------------------------------------------------------
# get_citation_network
# ---------------------------------------------------------------------------

class TestGetCitationNetwork:
    def test_returns_identifier_in_result(self, setup):
        tools, client = setup
        client.request_json.return_value = (ABSTRACT_RETRIEVAL_RESPONSE, MagicMock())
        client.get_with_pagination.return_value = []
        result = tools["get_citation_network"]("10.48550/arXiv.1706.03762")
        assert result["identifier"] == "10.48550/arXiv.1706.03762"

    def test_uses_doi_path_by_default(self, setup):
        tools, client = setup
        client.request_json.return_value = (ABSTRACT_RETRIEVAL_RESPONSE, MagicMock())
        client.get_with_pagination.return_value = []
        tools["get_citation_network"]("10.1/test")
        path = client.request_json.call_args[0][1]
        assert "/content/abstract/doi/10.1/test" == path

    def test_uses_eid_path_when_specified(self, setup):
        tools, client = setup
        client.request_json.return_value = (ABSTRACT_RETRIEVAL_RESPONSE, MagicMock())
        client.get_with_pagination.return_value = []
        tools["get_citation_network"]("2-s2.0-85045050056", identifier_type="eid")
        path = client.request_json.call_args[0][1]
        assert "/content/abstract/eid/" in path

    def test_follows_citingarticles_link(self, setup):
        tools, client = setup
        client.request_json.return_value = (ABSTRACT_RETRIEVAL_RESPONSE, MagicMock())
        client.get_with_pagination.return_value = [SEARCH_ENTRY]
        result = tools["get_citation_network"]("10.1/test")
        assert client.get_with_pagination.called
        assert result["citing_papers_count"] == 1

    def test_skips_pagination_when_no_citingarticles_link(self, setup):
        tools, client = setup
        no_link_response = {"abstracts-retrieval-response": ABS_NO_CITING_LINK}
        client.request_json.return_value = (no_link_response, MagicMock())
        result = tools["get_citation_network"]("10.1/test")
        assert not client.get_with_pagination.called
        assert result["citing_papers_count"] == 0

    def test_highly_cited_threshold_is_10(self, setup):
        tools, client = setup
        client.request_json.return_value = (ABSTRACT_RETRIEVAL_RESPONSE, MagicMock())
        low = {**SEARCH_ENTRY, "citedby-count": "5"}
        high = {**SEARCH_ENTRY, "citedby-count": "100"}
        exactly_10 = {**SEARCH_ENTRY, "citedby-count": "10"}
        client.get_with_pagination.return_value = [low, high, exactly_10]
        result = tools["get_citation_network"]("10.1/test")
        # Only papers with citation_count > 10 are "highly cited"
        assert all(p["citation_count"] > 10 for p in result["highly_cited_papers"])

    def test_citing_papers_sorted_by_citations_descending(self, setup):
        tools, client = setup
        client.request_json.return_value = (ABSTRACT_RETRIEVAL_RESPONSE, MagicMock())
        low = {**SEARCH_ENTRY, "citedby-count": "5"}
        high = {**SEARCH_ENTRY, "citedby-count": "99"}
        client.get_with_pagination.return_value = [low, high]
        result = tools["get_citation_network"]("10.1/test")
        counts = [p["citation_count"] for p in result["all_citing_papers"]]
        assert counts == sorted(counts, reverse=True)

    def test_none_response_returns_error(self, setup):
        tools, client = setup
        client.request_json.return_value = (None, MagicMock())
        result = tools["get_citation_network"]("10.1/missing")
        assert "error" in result

    def test_api_error_returns_error_dict(self, setup):
        tools, client = setup
        client.request_json.side_effect = ScopusApiError("Rate limit", 429)
        result = tools["get_citation_network"]("10.1/bad")
        assert "error" in result


# ---------------------------------------------------------------------------
# get_citation_metrics
# ---------------------------------------------------------------------------

# Citation metrics uses a different endpoint (/ws/rest/abstract/scopus/...) where
# citation-count is a list of {"$": "N"} dicts, matching ABSTRACT_RETRIEVAL_RESPONSE's
# coredata structure.

def _metrics_response(count: int, title: str) -> dict:
    return {
        "abstracts-retrieval-response": {
            "coredata": {
                "citation-count": [{"$": str(count)}],
                "dc:title": [{"$": title}],
            }
        }
    }


class TestGetCitationMetrics:
    def test_returns_all_identifiers(self, setup):
        tools, client = setup
        client.request_json.return_value = (_metrics_response(10, "Paper"), MagicMock())
        result = tools["get_citation_metrics"](["10.1/a", "10.1/b"])
        assert result["identifiers"] == ["10.1/a", "10.1/b"]

    def test_sorted_by_citation_count_descending(self, setup):
        tools, client = setup
        client.request_json.side_effect = [
            (_metrics_response(10, "Low Impact"), MagicMock()),
            (_metrics_response(100, "High Impact"), MagicMock()),
        ]
        result = tools["get_citation_metrics"](["10.1/low", "10.1/high"])
        assert result["metrics"][0]["citation_count"] == 100
        assert result["metrics"][1]["citation_count"] == 10

    def test_uses_ws_rest_endpoint(self, setup):
        tools, client = setup
        client.request_json.return_value = (_metrics_response(5, "Test"), MagicMock())
        tools["get_citation_metrics"](["10.1/test"])
        path = client.request_json.call_args[0][1]
        assert "/ws/rest/abstract/scopus/" in path

    def test_skips_failed_lookups_silently(self, setup):
        tools, client = setup
        client.request_json.side_effect = [
            ScopusApiError("Not found", 404),
            (_metrics_response(5, "Good"), MagicMock()),
        ]
        result = tools["get_citation_metrics"](["10.1/bad", "10.1/good"])
        assert len(result["metrics"]) == 1
        assert result["metrics"][0]["citation_count"] == 5

    def test_none_response_skipped(self, setup):
        tools, client = setup
        client.request_json.return_value = (None, MagicMock())
        result = tools["get_citation_metrics"](["10.1/missing"])
        assert result["metrics"] == []

    def test_empty_identifiers_list(self, setup):
        tools, client = setup
        result = tools["get_citation_metrics"]([])
        assert result["metrics"] == []
        assert not client.request_json.called

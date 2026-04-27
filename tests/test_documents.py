"""Tests for Story 1/3 — Document Tools: get_document_details, find_similar_documents, compare_documents."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, call

from scopus_mcp.scopus.client import ScopusApiError
from scopus_mcp.tools.documents import register_document_tools
from tests.conftest import (
    MockMCP,
    ABSTRACT_RETRIEVAL_RESPONSE,
    SEARCH_RESPONSE,
)


@pytest.fixture
def setup():
    mcp = MockMCP()
    client = MagicMock()
    register_document_tools(mcp, lambda: client)
    return mcp.tools, client


# ---------------------------------------------------------------------------
# get_document_details
# ---------------------------------------------------------------------------

class TestGetDocumentDetails:
    def test_returns_title_for_doi(self, setup):
        tools, client = setup
        client.request_json.return_value = (ABSTRACT_RETRIEVAL_RESPONSE, MagicMock())
        result = tools["get_document_details"]("10.48550/arXiv.1706.03762")
        assert result["title"] == "Attention Is All You Need"

    def test_doi_path_used_by_default(self, setup):
        tools, client = setup
        client.request_json.return_value = (ABSTRACT_RETRIEVAL_RESPONSE, MagicMock())
        tools["get_document_details"]("10.1234/test")
        path = client.request_json.call_args[0][1]
        assert "/content/abstract/doi/10.1234/test" == path

    def test_eid_path_when_specified(self, setup):
        tools, client = setup
        client.request_json.return_value = (ABSTRACT_RETRIEVAL_RESPONSE, MagicMock())
        tools["get_document_details"]("2-s2.0-85045050056", identifier_type="eid")
        path = client.request_json.call_args[0][1]
        assert "/content/abstract/eid/2-s2.0-85045050056" == path

    def test_pii_path_when_specified(self, setup):
        tools, client = setup
        client.request_json.return_value = (ABSTRACT_RETRIEVAL_RESPONSE, MagicMock())
        tools["get_document_details"]("S0004370221000199", identifier_type="pii")
        path = client.request_json.call_args[0][1]
        assert "/content/abstract/pii/S0004370221000199" == path

    def test_view_meta_abs_requested(self, setup):
        tools, client = setup
        client.request_json.return_value = (ABSTRACT_RETRIEVAL_RESPONSE, MagicMock())
        tools["get_document_details"]("10.1/test")
        params = client.request_json.call_args[1]["params"]
        assert params.get("view") == "META_ABS"

    def test_none_response_returns_error(self, setup):
        tools, client = setup
        client.request_json.return_value = (None, MagicMock())
        result = tools["get_document_details"]("10.1/missing")
        assert "error" in result

    def test_empty_abstracts_block_returns_error(self, setup):
        tools, client = setup
        client.request_json.return_value = ({"abstracts-retrieval-response": {}}, MagicMock())
        result = tools["get_document_details"]("10.1/bad")
        assert "error" in result

    def test_api_error_returns_error_dict(self, setup):
        tools, client = setup
        client.request_json.side_effect = ScopusApiError("Not found", 404)
        result = tools["get_document_details"]("10.1/bad")
        assert "error" in result

    def test_unknown_identifier_type_falls_back_to_doi(self, setup):
        tools, client = setup
        client.request_json.return_value = (ABSTRACT_RETRIEVAL_RESPONSE, MagicMock())
        tools["get_document_details"]("10.1/test", identifier_type="isbn")
        path = client.request_json.call_args[0][1]
        assert "/content/abstract/doi/" in path


# ---------------------------------------------------------------------------
# find_similar_documents
# ---------------------------------------------------------------------------

class TestFindSimilarDocuments:
    def test_first_six_title_words_used_for_search(self, setup):
        tools, client = setup
        long_title_abstract = {
            "abstracts-retrieval-response": {
                "dc:title": "One Two Three Four Five Six Seven Eight Nine",
                "prism:coverDate": "2023-01-01",
                "link": [],
            }
        }
        client.request_json.side_effect = [
            (long_title_abstract, MagicMock()),
            (SEARCH_RESPONSE, MagicMock()),
        ]
        tools["find_similar_documents"]("10.1/test")
        search_params = client.request_json.call_args[1]["params"]
        query = search_params["query"]
        assert "Six" in query
        assert "Seven" not in query

    def test_error_when_reference_doc_not_found(self, setup):
        tools, client = setup
        client.request_json.return_value = (None, MagicMock())
        result = tools["find_similar_documents"]("10.1/missing")
        assert "error" in result
        assert result["results"] == []

    def test_error_when_title_missing_from_doc(self, setup):
        tools, client = setup
        no_title = {"abstracts-retrieval-response": {"link": []}}
        client.request_json.return_value = (no_title, MagicMock())
        result = tools["find_similar_documents"]("10.1/notitle")
        assert "error" in result
        assert result["results"] == []

    def test_makes_two_api_calls(self, setup):
        tools, client = setup
        client.request_json.side_effect = [
            (ABSTRACT_RETRIEVAL_RESPONSE, MagicMock()),
            (SEARCH_RESPONSE, MagicMock()),
        ]
        tools["find_similar_documents"]("10.48550/arXiv.1706.03762")
        assert client.request_json.call_count == 2

    def test_api_error_on_retrieval_returns_error(self, setup):
        tools, client = setup
        client.request_json.side_effect = ScopusApiError("Server error", 500)
        result = tools["find_similar_documents"]("10.1/bad")
        assert "error" in result


# ---------------------------------------------------------------------------
# compare_documents
# ---------------------------------------------------------------------------

class TestCompareDocuments:
    def test_all_successful(self, setup):
        tools, client = setup
        client.request_json.return_value = (ABSTRACT_RETRIEVAL_RESPONSE, MagicMock())
        result = tools["compare_documents"](["10.1/a", "10.1/b"])
        assert result["successful_count"] == 2
        assert result["failed_count"] == 0
        assert len(result["documents"]) == 2

    def test_partial_failure_tracked(self, setup):
        tools, client = setup
        client.request_json.side_effect = [
            (ABSTRACT_RETRIEVAL_RESPONSE, MagicMock()),
            (None, MagicMock()),
        ]
        result = tools["compare_documents"](["10.1/ok", "10.1/missing"])
        assert result["successful_count"] == 1
        assert result["failed_count"] == 1
        assert len(result["errors"]) == 1

    def test_all_failed(self, setup):
        tools, client = setup
        client.request_json.side_effect = ScopusApiError("Service unavailable", 503)
        result = tools["compare_documents"](["10.1/a", "10.1/b"])
        assert result["successful_count"] == 0
        assert result["failed_count"] == 2

    def test_result_contains_identifiers(self, setup):
        tools, client = setup
        client.request_json.return_value = (ABSTRACT_RETRIEVAL_RESPONSE, MagicMock())
        result = tools["compare_documents"](["10.1/a", "10.1/b"])
        assert result["identifiers"] == ["10.1/a", "10.1/b"]

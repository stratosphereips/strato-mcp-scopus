"""Unit tests for summarize_document and summarize_author.

These are pure-function tests — no HTTP, no MCP. They pin exactly which
fields are extracted from each Scopus response shape and catch any silent
None-field regressions that would cause the agent to hallucinate.
"""
from __future__ import annotations

import pytest

from scopus_mcp.tools.authors import _author_retrieval_profile
from scopus_mcp.tools.schema import summarize_author, summarize_document
from tests.conftest import (
    ABSTRACT_RETRIEVAL_RESPONSE,
    AUTHOR_PROFILE_RESPONSE,
    AUTHOR_SEARCH_ENTRY,
    SEARCH_ENTRY,
)


class TestSummarizeDocumentFromSearchEntry:
    """summarize_document with a /content/search/scopus STANDARD-view entry."""

    def test_title(self):
        assert summarize_document(SEARCH_ENTRY)["title"] == "Cyber Deception: State of the Art"

    def test_authors_list(self):
        assert summarize_document(SEARCH_ENTRY)["authors"] == ["Achleitner S."]

    def test_year_extracted_from_cover_date(self):
        assert summarize_document(SEARCH_ENTRY)["year"] == "2023"

    def test_journal(self):
        assert summarize_document(SEARCH_ENTRY)["journal"] == "ACM Computing Surveys"

    def test_doi(self):
        assert summarize_document(SEARCH_ENTRY)["doi"] == "10.1145/3456789"

    def test_eid(self):
        assert summarize_document(SEARCH_ENTRY)["eid"] == "2-s2.0-85123456789"

    def test_citation_count_coerced_from_string(self):
        assert summarize_document(SEARCH_ENTRY)["citation_count"] == 42

    def test_abstract_snippet_present(self):
        snippet = summarize_document(SEARCH_ENTRY)["abstract_snippet"]
        assert snippet is not None
        assert "cyber deception" in snippet.lower()

    def test_self_link_extracted(self):
        link = summarize_document(SEARCH_ENTRY)["link"]
        assert link == "https://api.elsevier.com/content/abstract/eid/2-s2.0-85123456789"

    def test_abstract_truncated_at_200_chars(self):
        long_entry = {**SEARCH_ENTRY, "dc:description": "x" * 300}
        snippet = summarize_document(long_entry)["abstract_snippet"]
        assert snippet.endswith("...")
        assert len(snippet) == 203  # 200 chars + "..."

    def test_abstract_not_truncated_when_short(self):
        short_entry = {**SEARCH_ENTRY, "dc:description": "Short abstract."}
        snippet = summarize_document(short_entry)["abstract_snippet"]
        assert not snippet.endswith("...")

    def test_citation_count_none_becomes_zero(self):
        entry = {**SEARCH_ENTRY, "citedby-count": None}
        assert summarize_document(entry)["citation_count"] == 0

    def test_citation_count_missing_becomes_zero(self):
        entry = {k: v for k, v in SEARCH_ENTRY.items() if k != "citedby-count"}
        assert summarize_document(entry)["citation_count"] == 0

    def test_no_self_link_returns_none(self):
        entry = {**SEARCH_ENTRY, "link": [{"@ref": "scopus", "@href": "https://..."}]}
        assert summarize_document(entry)["link"] is None

    def test_missing_fields_return_none(self):
        result = summarize_document({})
        assert result["title"] is None
        assert result["authors"] == []
        assert result["year"] is None
        assert result["journal"] is None
        assert result["doi"] is None
        assert result["eid"] is None
        assert result["citation_count"] == 0
        assert result["abstract_snippet"] is None
        assert result["link"] is None


class TestSummarizeDocumentFromAbstractRetrieval:
    """summarize_document with a /content/abstract/doi/{doi} META_ABS response body."""

    def setup_method(self):
        # The tool extracts the inner dict before passing to summarize_document
        self.abstract_doc = ABSTRACT_RETRIEVAL_RESPONSE["abstracts-retrieval-response"]

    def test_title(self):
        assert summarize_document(self.abstract_doc)["title"] == "Attention Is All You Need"

    def test_doi(self):
        assert summarize_document(self.abstract_doc)["doi"] == "10.48550/arXiv.1706.03762"

    def test_year(self):
        assert summarize_document(self.abstract_doc)["year"] == "2017"

    def test_journal(self):
        result = summarize_document(self.abstract_doc)
        assert result["journal"] == "Advances in Neural Information Processing Systems"

    def test_abstract_snippet(self):
        snippet = summarize_document(self.abstract_doc)["abstract_snippet"]
        assert snippet is not None
        assert "sequence transduction" in snippet


class TestSummarizeAuthorFromSearchEntry:
    """summarize_author with an author-search STANDARD-view entry."""

    def test_full_name_assembled(self):
        assert summarize_author(AUTHOR_SEARCH_ENTRY)["name"] == "Geoffrey Hinton"

    def test_affiliation(self):
        assert summarize_author(AUTHOR_SEARCH_ENTRY)["affiliation"] == "University of Toronto"

    def test_author_id_prefix_stripped(self):
        author_id = summarize_author(AUTHOR_SEARCH_ENTRY)["author_id"]
        assert author_id == "35590507000"
        assert "AUTHOR_ID:" not in author_id

    def test_document_count(self):
        assert summarize_author(AUTHOR_SEARCH_ENTRY)["document_count"] == 250

    def test_citation_count(self):
        assert summarize_author(AUTHOR_SEARCH_ENTRY)["citation_count"] == 150000

    def test_h_index(self):
        assert summarize_author(AUTHOR_SEARCH_ENTRY)["h_index"] == 120

    def test_missing_fields_return_none_or_zero(self):
        result = summarize_author({})
        assert result["name"] is None
        assert result["affiliation"] is None
        assert result["author_id"] is None
        assert result["document_count"] == 0
        assert result["citation_count"] == 0
        assert result["h_index"] == 0


class TestSummarizeAuthorFromProfileResponse:
    """summarize_author with a /content/author/author_id/{id} ENHANCED response body,
    reshaped by _author_retrieval_profile as get_author_profile does."""

    def setup_method(self):
        self.profile = _author_retrieval_profile(AUTHOR_PROFILE_RESPONSE)

    def test_affiliation(self):
        assert summarize_author(self.profile)["affiliation"] == "University of Toronto"

    def test_full_name(self):
        assert summarize_author(self.profile)["name"] == "Geoffrey Hinton"

    def test_h_index(self):
        assert summarize_author(self.profile)["h_index"] == 120

    def test_author_id_no_prefix(self):
        assert summarize_author(self.profile)["author_id"] == "35590507000"

"""Shared fixtures and helpers for the test suite."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock


class MockMCP:
    """Minimal MCP stub that captures tool registrations."""

    def __init__(self):
        self.tools: dict[str, Any] = {}

    def tool(self, name: str | None = None, annotations=None):
        def decorator(fn):
            self.tools[name or fn.__name__] = fn
            return fn
        return decorator


def make_mock_client() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# Realistic Scopus response fixtures
# ---------------------------------------------------------------------------

# A single search-result entry as returned by /content/search/scopus (STANDARD view).
# Fields are at the top level of the entry dict; citedby-count is a plain string.
SEARCH_ENTRY = {
    "eid": "2-s2.0-85123456789",
    "dc:title": "Cyber Deception: State of the Art",
    "dc:creator": "Achleitner S.",
    "prism:publicationName": "ACM Computing Surveys",
    "prism:coverDate": "2023-06-01",
    "prism:doi": "10.1145/3456789",
    "citedby-count": "42",
    "dc:description": "This survey reviews the state of the art in cyber deception.",
    "link": [
        {"@ref": "self", "@href": "https://api.elsevier.com/content/abstract/eid/2-s2.0-85123456789"},
    ],
    "authoreference": [
        {
            "ce:indexed-name": "Achleitner S.",
            "@auid": "57123456789",
            "affiliation": [{"affiliation-name": {"#text": "Carnegie Mellon University"}}],
        }
    ],
}

SEARCH_RESPONSE = {
    "search-results": {
        "opensearch:totalResults": "1826",
        "entry": [SEARCH_ENTRY],
    }
}

EMPTY_SEARCH_RESPONSE = {
    "search-results": {
        "opensearch:totalResults": "0",
        "entry": [],
    }
}

# Abstract retrieval response as returned by /content/abstract/doi/{doi} (META_ABS view).
# Fields live inside "coredata"; citation-count is a list of {"$": "N"} dicts.
ABSTRACT_COREDATA = {
    "dc:title": "Attention Is All You Need",
    "prism:doi": "10.48550/arXiv.1706.03762",
    "prism:publicationName": "Advances in Neural Information Processing Systems",
    "prism:coverDate": "2017-12-01",
    "citation-count": [{"$": "50000"}],
    "citedby-count": "50000",
    "dc:description": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.",
    "link": [
        {"@rel": "self", "@href": "https://api.elsevier.com/content/abstract/doi/10.48550/arXiv.1706.03762"},
        {"@rel": "citingarticles", "@href": "https://api.elsevier.com/content/search/scopus?q=ref%2810.48550%2FarXiv.1706.03762%29"},
    ],
}

ABSTRACT_RETRIEVAL_RESPONSE = {
    "abstracts-retrieval-response": {
        "coredata": ABSTRACT_COREDATA,
        "eid": "2-s2.0-85045050056",
        # Some Scopus views also surface dc:title at this level
        "dc:title": "Attention Is All You Need",
        "prism:doi": "10.48550/arXiv.1706.03762",
        "prism:publicationName": "Advances in Neural Information Processing Systems",
        "prism:coverDate": "2017-12-01",
        "citedby-count": "50000",
        "dc:description": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.",
        "link": [
            {"@rel": "self", "@href": "https://api.elsevier.com/content/abstract/doi/10.48550/arXiv.1706.03762"},
            {"@rel": "citingarticles", "@href": "https://api.elsevier.com/content/search/scopus?q=ref%2810.48550%2FarXiv.1706.03762%29"},
        ],
    }
}

# Author search entry as returned by /content/search/author (STANDARD view).
AUTHOR_SEARCH_ENTRY = {
    "preferred-name": {"given-name": "Geoffrey", "surname": "Hinton"},
    "affiliation-current": {"affiliation-name": "University of Toronto"},
    "coredata": {
        "citation-count": "150000",
        "h-index": "120",
        "document-count": "250",
        "dc:identifier": "AUTHOR_ID:35590507000",
    },
}

AUTHOR_SEARCH_RESPONSE = {
    "search-results": {
        "opensearch:totalResults": "1",
        "entry": [AUTHOR_SEARCH_ENTRY],
    }
}

# Author profile as returned by /content/author/author_id/{id} (ENHANCED view): the record is
# wrapped in a one-element list; coredata and h-index sit next to author-profile, and the current
# affiliation's name is in affiliation-current.affiliation.ip-doc.
AUTHOR_PROFILE_RESPONSE = {
    "author-retrieval-response": [
        {
            "@status": "found",
            "coredata": {
                "citation-count": "150000",
                "document-count": "250",
                "dc:identifier": "AUTHOR_ID:35590507000",
            },
            "h-index": "120",
            "author-profile": {
                "preferred-name": {"given-name": "Geoffrey", "surname": "Hinton"},
                "affiliation-current": {
                    "affiliation": {
                        "@affiliation-id": "60016849",
                        "ip-doc": {
                            "@afdispname": "University of Toronto",
                            "preferred-name": {"$": "University of Toronto"},
                        },
                    }
                },
            },
        }
    ]
}


def make_count_response(count: int) -> dict:
    """Minimal Scopus search response that only carries a totalResults count."""
    return {
        "search-results": {
            "opensearch:totalResults": str(count),
            "entry": [],
        }
    }

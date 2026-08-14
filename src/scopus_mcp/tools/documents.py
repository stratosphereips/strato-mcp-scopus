"""Workflow-first tools for document retrieval and comparison."""
from __future__ import annotations

import logging
from typing import Any

from scopus_mcp.scopus.client import ScopusApiError
from scopus_mcp.tools import _resolve_id_field, _tool_annotations, summarize_document
from scopus_mcp.tools.discovery import _search_topic

logger = logging.getLogger(__name__)


def _get_document_metadata_fallback(
    client: Any,
    identifier: str,
    identifier_type: str,
    path: str,
) -> dict[str, Any]:
    """Retry an abstract-retrieval request with the metadata-only META view.

    Some API keys lack the entitlement required for the META_ABS view (which
    returns abstracts) and receive 401/403 instead. In that case we fall back to
    the META view, which returns the same metadata minus the abstract, so the
    tool still yields title, authors, journal, and citation count.
    """
    try:
        result, _ = client.request_json("GET", path, params={"view": "META"})
    except ScopusApiError as exc:
        logger.debug("META fallback failed for %r: %s", identifier, exc)
        return {
            "identifier": identifier,
            "identifier_type": identifier_type,
            "error": str(exc),
        }

    if result is None:
        return {
            "identifier": identifier,
            "identifier_type": identifier_type,
            "error": "Document not found",
        }

    abstract_doc = result.get("abstracts-retrieval-response", {})
    if not abstract_doc:
        return {
            "identifier": identifier,
            "identifier_type": identifier_type,
            "error": "Invalid response structure",
        }

    summary = summarize_document(abstract_doc)
    summary["abstract_snippet"] = None
    summary["abstract_available"] = False
    return summary


def register_document_tools(mcp: Any, get_client: Any) -> None:
    """Register document-focused Scopus tools."""

    @mcp.tool(
        name="get_document_details",
        annotations=_tool_annotations(read_only=True),
    )
    def get_document_details(
        identifier: str,
        identifier_type: str = "doi",
    ) -> dict[str, Any]:
        """Retrieve full metadata for a specific document.

        Get comprehensive information about a paper including abstract, authors,
        citations, and references.

        Use this when you want to:
        - "Show me the abstract of this paper"
        - "Get full details for DOI: 10.1038/s41586-023-06090-9"

        Args:
            identifier: The document identifier (DOI, EID, or PII)
            identifier_type: Type of identifier — "doi", "eid", or "pii"

        Returns:
            Complete document metadata including abstract, authors, citations
        """
        client = get_client()
        id_field = _resolve_id_field(identifier_type)
        path = f"/content/abstract/{id_field}/{identifier}"

        try:
            result, _ = client.request_json(
                "GET",
                path,
                params={"view": "META_ABS"},
            )

            if result is None:
                return {
                    "identifier": identifier,
                    "identifier_type": identifier_type,
                    "error": "Document not found",
                }

            abstract_doc = result.get("abstracts-retrieval-response", {})
            if not abstract_doc:
                return {
                    "identifier": identifier,
                    "identifier_type": identifier_type,
                    "error": "Invalid response structure",
                }

            summary = summarize_document(abstract_doc)
            summary["abstract_available"] = summary.get("abstract_snippet") is not None
            return summary

        except ScopusApiError as exc:
            if exc.status_code in (401, 403):
                return _get_document_metadata_fallback(
                    client, identifier, identifier_type, path
                )
            logger.debug("get_document_details failed for %r", identifier, exc_info=True)
            return {
                "identifier": identifier,
                "identifier_type": identifier_type,
                "error": str(exc),
            }

        except Exception as exc:
            logger.debug("get_document_details failed for %r", identifier, exc_info=True)
            return {
                "identifier": identifier,
                "identifier_type": identifier_type,
                "error": str(exc),
            }

    @mcp.tool(
        name="find_similar_documents",
        annotations=_tool_annotations(read_only=True),
    )
    def find_similar_documents(
        identifier: str,
        identifier_type: str = "doi",
        limit: int = 5,
    ) -> dict[str, Any]:
        """Find papers similar to a given document.

        Discovers related research by extracting the reference document's title
        and searching for papers with overlapping terminology.

        Use this when you want to:
        - "What papers are similar to this one?"
        - "Find related work on this topic"

        Args:
            identifier: The reference document identifier (DOI, EID, or PII)
            identifier_type: Type of identifier — "doi", "eid", or "pii"
            limit: Maximum number of similar documents to return

        Returns:
            List of similar documents with summaries
        """
        client = get_client()

        try:
            doc_result = get_document_details(identifier, identifier_type)

            if "error" in doc_result:
                return {
                    "identifier": identifier,
                    "error": f"Could not retrieve reference document: {doc_result['error']}",
                    "results": [],
                }

            title = doc_result.get("title", "")
            if not title:
                return {
                    "identifier": identifier,
                    "error": "Could not extract title from document",
                    "results": [],
                }

            # Use the first six title words as a keyword probe; a full title search
            # tends to return zero results due to exact-phrase matching edge cases.
            query_words = " ".join(title.split()[:6])
            return _search_topic(client, query_words, years_back=5, limit=limit, sort_by="relevance")

        except Exception as exc:
            logger.debug("find_similar_documents failed for %r", identifier, exc_info=True)
            return {"identifier": identifier, "error": str(exc), "results": []}

    @mcp.tool(
        name="compare_documents",
        annotations=_tool_annotations(read_only=True),
    )
    def compare_documents(
        identifiers: list[str],
        identifier_type: str = "doi",
    ) -> dict[str, Any]:
        """Compare multiple documents side by side.

        Get a structured comparison of papers with key fields aligned for easy
        contrast of methods, publication venues, and citation impact.

        Use this when you want to:
        - "Compare these three papers on transformer models"
        - "What's the difference between these approaches?"

        Args:
            identifiers: List of document identifiers to compare
            identifier_type: Type of identifiers — "doi", "eid", or "pii"

        Returns:
            Side-by-side comparison with key fields aligned
        """
        results = []
        errors = []

        for ident in identifiers:
            try:
                doc = get_document_details(ident, identifier_type)
                if "error" in doc:
                    errors.append({"identifier": ident, "error": doc["error"]})
                else:
                    results.append(doc)
            except Exception as exc:
                logger.debug("compare_documents failed for %r", ident, exc_info=True)
                errors.append({"identifier": ident, "error": str(exc)})

        return {
            "identifiers": identifiers,
            "successful_count": len(results),
            "failed_count": len(errors),
            "documents": results,
            "errors": errors,
        }

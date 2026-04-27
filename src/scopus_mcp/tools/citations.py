"""Workflow-first tools for citation analysis."""
from __future__ import annotations

import logging
from typing import Any

from scopus_mcp.tools import (
    _resolve_id_field,
    _tool_annotations,
    parse_citation_count,
    summarize_document,
)

logger = logging.getLogger(__name__)

# Papers with at least this many citations are surfaced as "highly cited".
_HIGHLY_CITED_THRESHOLD = 10


def register_citation_tools(mcp: Any, get_client: Any) -> None:
    """Register citation-focused Scopus tools."""

    @mcp.tool(
        name="get_citation_network",
        annotations=_tool_annotations(read_only=True),
    )
    def get_citation_network(
        identifier: str,
        identifier_type: str = "doi",
        max_citations: int = 50,
    ) -> dict[str, Any]:
        """Get the citation network for a document.

        Retrieve forward citations (papers that cite this one) to understand how
        research connects and which follow-up work has had the most impact.

        Use this when you want to:
        - "What papers cite this one?"
        - "How has this idea evolved through citations?"
        - "Find the most influential follow-up papers"

        Args:
            identifier: The document identifier (DOI, EID, or PII)
            identifier_type: Type of identifier — "doi", "eid", or "pii"
            max_citations: Maximum citing papers to retrieve

        Returns:
            Citation network with forward citations sorted by impact
        """
        client = get_client()
        id_field = _resolve_id_field(identifier_type)

        try:
            result, _ = client.request_json(
                "GET",
                f"/content/abstract/{id_field}/{identifier}",
                params={"view": "META_ABS"},
            )

            if result is None:
                return {"identifier": identifier, "error": "Document not found"}

            abstract_doc = result.get("abstracts-retrieval-response", {})
            if not abstract_doc:
                return {"identifier": identifier, "error": "Invalid response structure"}

            coredata = abstract_doc.get("coredata", {})
            citation_count = parse_citation_count(coredata.get("citation-count"))

            citing_url = next(
                (
                    link.get("@href", "")
                    for link in coredata.get("link", [])
                    if isinstance(link, dict) and link.get("@rel") == "citingarticles"
                ),
                "",
            )

            citing_papers: list[dict[str, Any]] = []
            if citing_url:
                citing_path = citing_url.replace("https://api.elsevier.com", "")
                raw = client.get_with_pagination(citing_path, max_results=max_citations)
                citing_papers = [summarize_document(e) for e in raw]

            citing_papers.sort(key=lambda x: x.get("citation_count", 0), reverse=True)
            highly_cited = [
                p for p in citing_papers if p.get("citation_count", 0) > _HIGHLY_CITED_THRESHOLD
            ]

            return {
                "identifier": identifier,
                "document": summarize_document(abstract_doc),
                "citation_count": citation_count,
                "citing_papers_count": len(citing_papers),
                "highly_cited_papers": highly_cited,
                "all_citing_papers": citing_papers[:max_citations],
            }

        except Exception as exc:
            logger.debug("get_citation_network failed for %r", identifier, exc_info=True)
            return {"identifier": identifier, "error": str(exc)}

    @mcp.tool(
        name="get_citation_metrics",
        annotations=_tool_annotations(read_only=True),
    )
    def get_citation_metrics(
        identifiers: list[str],
        identifier_type: str = "doi",
    ) -> dict[str, Any]:
        """Get citation metrics for multiple documents.

        Compare citation counts across papers to identify the most influential work.

        Use this when you want to:
        - "Which of these papers has the most citations?"
        - "Compare the impact of these publications"

        Args:
            identifiers: List of document identifiers
            identifier_type: Type of identifiers — "doi", "eid", or "pii"

        Returns:
            Citation metrics sorted by impact
        """
        client = get_client()
        id_field = _resolve_id_field(identifier_type)

        metrics: list[dict[str, Any]] = []

        for ident in identifiers:
            try:
                result, _ = client.request_json(
                    "GET",
                    f"/ws/rest/abstract/scopus/{id_field}/{ident}",
                    params={"view": "META"},
                )
                if result is None:
                    continue

                coredata = result.get("abstracts-retrieval-response", {}).get("coredata", {})
                citation_count = parse_citation_count(coredata.get("citation-count"))

                # dc:title can be a plain string or a list of {"$": "..."} dicts
                raw_title = coredata.get("dc:title")
                if isinstance(raw_title, list):
                    title = next(
                        (
                            (item.get("$") or item.get("#text"))
                            for item in raw_title
                            if isinstance(item, dict)
                        ),
                        None,
                    )
                else:
                    title = raw_title

                metrics.append(
                    {"identifier": ident, "title": title, "citation_count": citation_count}
                )

            except Exception:
                logger.debug("get_citation_metrics failed for %r", ident, exc_info=True)

        metrics.sort(key=lambda x: x.get("citation_count", 0), reverse=True)
        return {"identifiers": identifiers, "metrics": metrics}

"""Workflow-first tools for literature discovery and exploration."""
from __future__ import annotations

import datetime
import logging
from typing import Any

from scopus_mcp.tools import _tool_annotations, summarize_document

logger = logging.getLogger(__name__)


def _search_topic(
    client: Any,
    topic: str,
    years_back: int = 2,
    limit: int = 15,
    sort_by: str = "cited_by_count",
) -> dict[str, Any]:
    """Core topic search logic, callable without going through the MCP tool layer."""
    current_year = datetime.date.today().year
    from_year = current_year - years_back
    query = f"TITLE-ABS-KEY({topic}) AND PUBYEAR > {from_year - 1}"

    sort_map = {
        "cited_by_count": "citedby-count",
        "date": "pubyear",
        "relevance": None,
    }
    sort_param = sort_map.get(sort_by)

    path = "/content/search/scopus"
    params: dict[str, Any] = {
        "query": query,
        "count": min(limit, 100),
        "view": "STANDARD",
    }
    if sort_param:
        params["sort"] = sort_param

    result, _ = client.request_json("GET", path, params=params)

    if result is None:
        return {
            "topic": topic,
            "query": query,
            "total_results": 0,
            "results": [],
        }

    entries = result.get("search-results", {}).get("entry", [])
    summaries = [summarize_document(e) for e in entries[:limit]]

    if sort_by == "cited_by_count":
        summaries.sort(key=lambda x: x.get("citation_count", 0), reverse=True)
    elif sort_by == "date":
        summaries.sort(key=lambda x: x.get("year", "0"), reverse=True)

    total_results = int(
        result.get("search-results", {}).get("opensearch:totalResults", len(summaries))
    )

    return {
        "topic": topic,
        "query": query,
        "from_year": from_year,
        "total_results": total_results,
        "results": summaries,
    }


def register_discovery_tools(mcp: Any, get_client: Any) -> None:
    """Register discovery-focused Scopus tools."""

    @mcp.tool(
        name="explore_topic",
        annotations=_tool_annotations(read_only=True),
    )
    def explore_topic(
        topic: str,
        years_back: int = 2,
        limit: int = 15,
        sort_by: str = "cited_by_count",
    ) -> dict[str, Any]:
        """Explore research on a specific topic and find relevant papers.

        This is the primary tool for literature discovery. It searches Scopus for papers
        on your topic, sorted by relevance or citations, and returns agent-friendly summaries.

        Use this when you want to:
        - "Find me recent papers on transformer models for protein folding"
        - "What's new in climate change adaptation research?"
        - "Show me the most cited papers on quantum computing"

        Args:
            topic: The research topic to search for (e.g., "transformer models protein folding")
            years_back: How many years of recent research to include (default: 2)
            limit: Maximum number of results to return (default: 15)
            sort_by: Sort criteria - "cited_by_count" (most cited), "date" (newest), or "relevance"

        Returns:
            List of papers with titles, authors, years, journals, citation counts, and abstract snippets
        """
        client = get_client()
        try:
            return _search_topic(client, topic, years_back, limit, sort_by)
        except Exception as exc:
            logger.debug("explore_topic failed for topic=%r", topic, exc_info=True)
            return {
                "topic": topic,
                "error": str(exc),
                "results": [],
            }

    @mcp.tool(
        name="advanced_search",
        annotations=_tool_annotations(read_only=True),
    )
    def advanced_search(
        title: str | None = None,
        author: str | None = None,
        affiliation: str | None = None,
        keywords: str | None = None,
        year: str | None = None,
        doc_type: str | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
        """Perform a structured search without needing Scopus query syntax knowledge.

        Build a search from components instead of writing complex queries. Useful when
        you know specific criteria but don't want to learn Scopus's query language.

        Use this when you want to:
        - "Find articles by Hinton on neural networks from 2023"
        - "Search for papers from MIT on machine learning"
        - "Find review articles on CRISPR from the last 3 years"

        Args:
            title: Words that must appear in the title
            author: Author name to search for
            affiliation: Institution/affiliation to filter by
            keywords: Keywords to search in title, abstract, and keywords fields
            year: Specific year or year range (e.g., "2023" or "2020-2024")
            doc_type: Document type filter ("ar"=article, "re"=review, "ch"=chapter)
            limit: Maximum number of results (default: 25)

        Returns:
            Search results with document summaries
        """
        client = get_client()

        query_parts = []

        if title:
            query_parts.append(f"TITLE({title})")
        if author:
            query_parts.append(f"AUTH({author})")
        if affiliation:
            query_parts.append(f"AFFIL({affiliation})")
        if keywords:
            query_parts.append(f"TITLE-ABS-KEY({keywords})")
        if year:
            if "-" in year:
                start, end = year.split("-", 1)
                query_parts.append(f"PUBYEAR >= {start} AND PUBYEAR <= {end}")
            else:
                query_parts.append(f"PUBYEAR = {year}")
        if doc_type:
            query_parts.append(f"DOCTYPE({doc_type})")

        if not query_parts:
            return {
                "error": "At least one search criterion must be provided",
                "results": [],
            }

        query = " AND ".join(query_parts)

        try:
            path = "/content/search/scopus"
            params: dict[str, Any] = {
                "query": query,
                "count": min(limit, 100),
                "view": "STANDARD",
            }

            result, _ = client.request_json("GET", path, params=params)

            if result is None:
                return {
                    "query": query,
                    "total_results": 0,
                    "results": [],
                }

            entries = result.get("search-results", {}).get("entry", [])
            summaries = [summarize_document(e) for e in entries]

            total_results = int(
                result.get("search-results", {}).get("opensearch:totalResults", len(summaries))
            )

            return {
                "query": query,
                "total_results": total_results,
                "results": summaries,
            }

        except Exception as exc:
            logger.debug("advanced_search failed for query=%r", query, exc_info=True)
            return {
                "query": query,
                "error": str(exc),
                "results": [],
            }

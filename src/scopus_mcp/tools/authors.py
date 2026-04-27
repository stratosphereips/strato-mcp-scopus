"""Workflow-first tools for author discovery and profiling."""
from __future__ import annotations

import datetime
import logging
from typing import Any

from scopus_mcp.tools import (
    _resolve_id_field,
    _tool_annotations,
    parse_citation_count,
    summarize_author,
    summarize_document,
)

logger = logging.getLogger(__name__)


def register_author_tools(mcp: Any, get_client: Any) -> None:
    """Register author-focused Scopus tools."""

    @mcp.tool(
        name="find_experts_in",
        annotations=_tool_annotations(read_only=True),
    )
    def find_experts_in(
        topic: str,
        field: str | None = None,
        limit: int = 5,
        years_back: int = 3,
    ) -> dict[str, Any]:
        """Discover key researchers working on a specific topic.

        Search for recent high-impact papers on a topic and extract the most
        prominent authors based on their contributions and citation impact.

        Use this when you want to:
        - "Who are the key researchers in single-cell RNA sequencing?"
        - "Find leading authors on transformer models"
        - "Who's doing important work in climate adaptation?"

        Args:
            topic: The research topic to find experts in
            field: Optional subject area to narrow search (e.g. "COMP", "MEDI")
            limit: Maximum number of experts to return
            years_back: How many years of recent research to consider

        Returns:
            Ranked list of researchers with affiliations and metrics
        """
        client = get_client()

        current_year = datetime.date.today().year
        from_year = current_year - years_back

        query_parts = [f"TITLE-ABS-KEY({topic})"]
        if field:
            query_parts.append(f"SUBJAREA({field})")
        query_parts.append(f"PUBYEAR > {from_year - 1}")
        query = " AND ".join(query_parts)

        try:
            result, _ = client.request_json(
                "GET",
                "/content/search/scopus",
                params={
                    "query": query,
                    "count": min(limit * 10, 100),
                    "view": "STANDARD",
                    "sort": "citedby-count",
                },
            )

            if result is None:
                return {"topic": topic, "field": field, "experts": []}

            entries = result.get("search-results", {}).get("entry", [])
            author_stats: dict[str, dict[str, Any]] = {}

            for entry in entries[:50]:
                # Search results return citedby-count as a plain string.
                citations = parse_citation_count(entry.get("citedby-count"))

                for author in entry.get("authoreference", [])[:5]:
                    if not isinstance(author, dict):
                        continue

                    author_id = author.get("@auid")
                    if not author_id:
                        continue

                    author_name = author.get("ce:indexed-name") or author.get("dc:creator")
                    if not author_name:
                        continue

                    affiliation: str | None = None
                    for aff in author.get("affiliation", []):
                        if isinstance(aff, dict):
                            affiliation = (
                                aff.get("affiliation-name", {}).get("#text")
                                or aff.get("affilname")
                            )
                            if affiliation:
                                break

                    if author_id not in author_stats:
                        author_stats[author_id] = {
                            "name": str(author_name),
                            "author_id": author_id,
                            "affiliation": affiliation,
                            "paper_count": 0,
                            "total_citations": 0,
                        }

                    author_stats[author_id]["paper_count"] += 1
                    author_stats[author_id]["total_citations"] += citations

            experts = sorted(
                author_stats.values(),
                key=lambda x: (x["total_citations"], x["paper_count"]),
                reverse=True,
            )

            return {
                "topic": topic,
                "field": field,
                "from_year": from_year,
                "experts": experts[:limit],
            }

        except Exception as exc:
            logger.debug("find_experts_in failed for topic=%r", topic, exc_info=True)
            return {"topic": topic, "field": field, "error": str(exc), "experts": []}

    @mcp.tool(
        name="search_author",
        annotations=_tool_annotations(read_only=True),
    )
    def search_author(
        author_name: str,
        affiliation: str | None = None,
    ) -> dict[str, Any]:
        """Search for authors by name with disambiguation support.

        Find researchers by name, handling cases where multiple authors share
        the same name.

        Use this when you want to:
        - "Find Geoffrey Hinton's profile"
        - "Search for authors named Smith working at MIT"

        Args:
            author_name: The author's name to search for
            affiliation: Optional affiliation to help disambiguate

        Returns:
            List of matching authors with basic info for selection
        """
        client = get_client()

        query = f"AUTHNAME({author_name})"
        if affiliation:
            query += f" AND AFFIL({affiliation})"

        try:
            result, _ = client.request_json(
                "GET",
                "/content/search/author",
                params={"query": query, "count": 10, "view": "STANDARD"},
            )

            if result is None:
                return {"query": author_name, "total_results": 0, "results": []}

            authors = result.get("search-results", {}).get("entry", [])
            summaries = [summarize_author(a) for a in authors]

            return {
                "query": author_name,
                "total_results": len(summaries),
                "results": summaries,
            }

        except Exception as exc:
            logger.debug("search_author failed for %r", author_name, exc_info=True)
            return {"query": author_name, "error": str(exc), "results": []}

    @mcp.tool(
        name="get_author_profile",
        annotations=_tool_annotations(read_only=True),
    )
    def get_author_profile(
        author_id: str,
        include_publications: bool = False,
        publication_limit: int = 10,
    ) -> dict[str, Any]:
        """Get a comprehensive author profile.

        Retrieve full publication history, citation metrics, h-index, and
        affiliation for a researcher.

        Use this when you want to:
        - "Tell me more about this researcher"
        - "What are their most cited recent papers?"
        - "Get their full publication profile"

        Args:
            author_id: The Scopus author ID
            include_publications: Whether to include recent publications
            publication_limit: Max publications to include if requested

        Returns:
            Complete author profile with metrics and optionally publications
        """
        client = get_client()

        try:
            result, _ = client.request_json(
                "GET",
                f"/content/author/author_id/{author_id}",
                params={"view": "COMPLETE"},
            )

            if result is None:
                return {"author_id": author_id, "error": "Author not found"}

            profile_data = result.get("author-profile", {})
            summary = summarize_author(profile_data)

            if include_publications:
                documents = profile_data.get("data", {}).get("document", [])
                summary["recent_publications"] = [
                    summarize_document(doc) for doc in documents[:publication_limit]
                ]

            return summary

        except Exception as exc:
            logger.debug("get_author_profile failed for author_id=%r", author_id, exc_info=True)
            return {"author_id": author_id, "error": str(exc)}

    @mcp.tool(
        name="compare_authors",
        annotations=_tool_annotations(read_only=True),
    )
    def compare_authors(
        author_ids: list[str],
    ) -> dict[str, Any]:
        """Compare multiple authors side by side.

        Get a structured comparison of researchers highlighting differences in
        publication count, citations, h-index, and research focus.

        Use this when you want to:
        - "Compare these researchers in the field"
        - "Who has more impact in this area?"

        Args:
            author_ids: List of Scopus author IDs to compare

        Returns:
            Side-by-side comparison with key metrics aligned
        """
        results = []
        errors = []

        for aid in author_ids:
            try:
                profile = get_author_profile(aid, include_publications=False)
                if "error" in profile:
                    errors.append({"author_id": aid, "error": profile["error"]})
                else:
                    results.append(profile)
            except Exception as exc:
                logger.debug("compare_authors failed for author_id=%r", aid, exc_info=True)
                errors.append({"author_id": aid, "error": str(exc)})

        return {
            "author_ids": author_ids,
            "successful_count": len(results),
            "failed_count": len(errors),
            "authors": results,
            "errors": errors,
        }

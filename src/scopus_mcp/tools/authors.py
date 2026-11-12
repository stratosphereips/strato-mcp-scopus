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


def _as_list(value: Any) -> list[Any]:
    """Scopus JSON gives a one-element list as a bare object: always return a list."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _author_retrieval_profile(result: dict[str, Any]) -> dict[str, Any]:
    """Reshape an Author Retrieval response into the structure summarize_author reads.

    The API wraps the record as ``{"author-retrieval-response": [entry]}``. In the entry,
    ``coredata`` and ``h-index`` sit next to ``author-profile``, not inside it, and the current
    affiliation's name is in ``affiliation-current.affiliation[].ip-doc`` (``@afdispname`` or
    ``preferred-name.$``).
    """
    entry: Any = result.get("author-retrieval-response", result)
    if isinstance(entry, list):
        entry = entry[0] if entry else {}
    if not isinstance(entry, dict):
        entry = {}

    profile = dict(entry.get("author-profile") or {})
    coredata = dict(entry.get("coredata") or profile.get("coredata") or {})
    if entry.get("h-index") is not None:
        coredata.setdefault("h-index", entry["h-index"])
    profile["coredata"] = coredata

    current = profile.get("affiliation-current")
    if isinstance(current, dict) and "affiliation" in current:
        name = None
        for aff in _as_list(current["affiliation"]):
            doc = (aff.get("ip-doc") or {}) if isinstance(aff, dict) else {}
            preferred = doc.get("preferred-name")
            name = doc.get("@afdispname") or doc.get("afdispname") or (
                preferred.get("$") if isinstance(preferred, dict) else preferred
            )
            if name:
                break
        profile["affiliation-current"] = {"affiliation-name": name}

    return {"author-profile": profile}


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
            # Only the COMPLETE view lists every author of a result (STANDARD carries just
            # dc:creator), and the API returns at most 25 entries per page.
            wanted = min(limit * 10, 100)
            entries: list[dict[str, Any]] = []
            while len(entries) < wanted:
                result, _ = client.request_json(
                    "GET",
                    "/content/search/scopus",
                    params={
                        "query": query,
                        "start": len(entries),
                        "count": min(25, wanted - len(entries)),
                        "view": "COMPLETE",
                        "sort": "citedby-count",
                    },
                )
                if result is None:
                    break
                page = result.get("search-results", {}).get("entry", [])
                # An empty result set comes back as one entry that only carries an "error" key.
                page = [e for e in page if isinstance(e, dict) and "error" not in e]
                entries.extend(page)
                total = int(result.get("search-results", {}).get("opensearch:totalResults", 0) or 0)
                if not page or len(entries) >= total:
                    break

            author_stats: dict[str, dict[str, Any]] = {}

            for entry in entries:
                # Search results return citedby-count as a plain string.
                citations = parse_citation_count(entry.get("citedby-count"))
                affiliation_names = {
                    aff.get("afid"): aff.get("affilname")
                    for aff in _as_list(entry.get("affiliation"))
                    if isinstance(aff, dict)
                }

                for author in _as_list(entry.get("author"))[:5]:
                    if not isinstance(author, dict):
                        continue

                    author_id = author.get("authid")
                    if not author_id:
                        continue

                    author_name = author.get("authname") or " ".join(
                        part for part in (author.get("given-name"), author.get("surname")) if part
                    )
                    if not author_name:
                        continue

                    affiliation: str | None = None
                    for afid in _as_list(author.get("afid")):
                        name = affiliation_names.get(afid.get("$") if isinstance(afid, dict) else afid)
                        if name:
                            affiliation = name
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
            # Author Retrieval accepts LIGHT, STANDARD and ENHANCED; ENHANCED adds the h-index.
            result, _ = client.request_json(
                "GET",
                f"/content/author/author_id/{author_id}",
                params={"view": "ENHANCED"},
            )

            if result is None:
                return {"author_id": author_id, "error": "Author not found"}

            summary = summarize_author(_author_retrieval_profile(result))

            if include_publications:
                # Author Retrieval carries no document list: search the author's documents.
                docs, _ = client.request_json(
                    "GET",
                    "/content/search/scopus",
                    params={
                        "query": f"AU-ID({author_id})",
                        "count": max(1, min(publication_limit, 25)),
                        "sort": "-coverDate",
                        "view": "STANDARD",
                    },
                )
                entries = (docs or {}).get("search-results", {}).get("entry", [])
                summary["recent_publications"] = [
                    summarize_document(doc)
                    for doc in entries[:publication_limit]
                    if isinstance(doc, dict) and "error" not in doc
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

"""Workflow-first tools for research trend analysis."""
from __future__ import annotations

import datetime
import logging
from typing import Any

from scopus_mcp.tools import _tool_annotations

logger = logging.getLogger(__name__)


def _parse_timespan(timespan: str) -> tuple[int, int]:
    """Parse ``'YYYY-YYYY'`` or ``'YYYY'`` into ``(start_year, end_year)``.

    Raises ``ValueError`` if the string cannot be parsed into integers.
    """
    if "-" in timespan:
        raw_start, raw_end = timespan.split("-", 1)
        return int(raw_start), int(raw_end)
    year = int(timespan)
    return year, datetime.date.today().year


def _count_for_year(client: Any, query_base: str, year: int) -> int:
    """Return the total Scopus result count for *topic* in *year*.

    Fetches only a single result (``count=1``) so the API call is cheap; the
    count is read from the ``opensearch:totalResults`` header field.
    """
    result, _ = client.request_json(
        "GET",
        "/content/search/scopus",
        params={
            "query": f"{query_base} AND PUBYEAR = {year}",
            "count": 1,
            "view": "STANDARD",
        },
    )
    if result is None:
        return 0
    return int(result.get("search-results", {}).get("opensearch:totalResults", 0))


def _classify_trend(yearly_counts: list[dict[str, Any]]) -> str:
    """Classify the overall publication trajectory from yearly counts.

    Returns one of: ``"growing"``, ``"declining"``, ``"stable"``, ``"peaked"``,
    or ``"insufficient data"``.
    """
    counts = [e["count"] for e in yearly_counts]
    if len(counts) < 2:
        return "insufficient data"

    mid = len(counts) // 2
    first_half_avg = sum(counts[:mid]) / mid
    second_half_avg = sum(counts[mid:]) / (len(counts) - mid)

    # Detect a rise-then-fall pattern: peak must be interior (not at index 0)
    # and the final value must have fallen to below 60 % of the peak.
    peak_count = max(counts)
    peak_idx = counts.index(peak_count)
    last_count = counts[-1]
    if (
        peak_idx > 0
        and peak_idx < len(counts) - 2
        and peak_count > 0
        and last_count / peak_count < 0.6
    ):
        return "peaked"

    if first_half_avg == 0:
        return "growing" if second_half_avg > 0 else "stable"

    change = (second_half_avg - first_half_avg) / first_half_avg
    if change > 0.15:
        return "growing"
    if change < -0.15:
        return "declining"
    return "stable"


def _analyze_trends_impl(
    client: Any,
    topic: str,
    timespan: str,
) -> dict[str, Any]:
    """Core trend-analysis logic, separated from the MCP tool layer for testability."""
    try:
        start_year, end_year = _parse_timespan(timespan)
    except ValueError:
        return {
            "topic": topic,
            "timespan": timespan,
            "error": f"Invalid timespan {timespan!r}. Use 'YYYY-YYYY' or 'YYYY'.",
        }

    current_year = datetime.date.today().year
    end_year = min(end_year, current_year)

    if start_year > end_year:
        return {
            "topic": topic,
            "timespan": timespan,
            "error": (
                f"Invalid timespan: start year {start_year} is after end year {end_year}."
            ),
        }

    if start_year > current_year:
        return {
            "topic": topic,
            "timespan": timespan,
            "error": f"Start year {start_year} is in the future; no data available.",
        }

    query_base = f"TITLE-ABS-KEY({topic})"
    yearly_counts: list[dict[str, Any]] = [
        {"year": year, "count": _count_for_year(client, query_base, year)}
        for year in range(start_year, end_year + 1)
    ]

    total_publications = sum(e["count"] for e in yearly_counts)
    peak_entry = max(yearly_counts, key=lambda e: e["count"])
    lowest_entry = min(yearly_counts, key=lambda e: e["count"])

    mid = len(yearly_counts) // 2
    first_half_avg = sum(e["count"] for e in yearly_counts[:mid]) / mid if mid > 0 else 0.0
    tail = yearly_counts[mid:]
    second_half_avg = sum(e["count"] for e in tail) / len(tail) if tail else 0.0

    if first_half_avg > 0:
        growth_rate_pct = round(
            (second_half_avg - first_half_avg) / first_half_avg * 100, 1
        )
    else:
        growth_rate_pct = None

    return {
        "topic": topic,
        "timespan": f"{start_year}-{end_year}",
        "start_year": start_year,
        "end_year": end_year,
        "total_publications": total_publications,
        "yearly_counts": yearly_counts,
        "peak_year": peak_entry["year"],
        "growth": {
            "first_half_avg": round(first_half_avg, 1),
            "second_half_avg": round(second_half_avg, 1),
            "growth_rate_pct": growth_rate_pct,
            "trend": _classify_trend(yearly_counts),
        },
        "notable_years": {
            "peak": peak_entry,
            "lowest": lowest_entry,
        },
    }


def register_trend_tools(mcp: Any, get_client: Any) -> None:
    """Register trend analysis tools."""

    @mcp.tool(
        name="analyze_trends",
        annotations=_tool_annotations(read_only=True),
    )
    def analyze_trends(
        topic: str,
        timespan: str = "2015-2025",
    ) -> dict[str, Any]:
        """Analyze how research on a topic has evolved over time.

        Tracks publication volume year by year and identifies whether a field is
        growing, declining, stable, or has peaked. Useful for understanding the
        trajectory of a research area before diving into specific papers.

        Use this when you want to:
        - "How has research on quantum computing in chemistry evolved over the past decade?"
        - "Is cyber deception a growing field?"
        - "When did deep learning really take off?"

        Args:
            topic: The research topic to analyze (e.g., "quantum computing chemistry")
            timespan: Year range in ``'YYYY-YYYY'`` format (default: ``"2015-2025"``)

        Returns:
            Yearly publication counts, peak year, growth rate, and trajectory classification
        """
        client = get_client()
        try:
            return _analyze_trends_impl(client, topic, timespan)
        except Exception as exc:
            logger.debug("analyze_trends failed for topic=%r", topic, exc_info=True)
            return {"topic": topic, "timespan": timespan, "error": str(exc)}

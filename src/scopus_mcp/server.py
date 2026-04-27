"""MCP server entry point for Scopus."""
from __future__ import annotations

import logging
import sys
import threading

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

SERVER_INSTRUCTIONS = """
This server helps researchers discover and explore academic literature using Scopus.
It focuses on workflow-first tools for literature discovery, not raw API endpoints.

Key workflows:

1. **Finding papers on a topic**: Use `explore_topic(topic="...", years_back=2)` to discover relevant papers
2. **Finding researchers**: Use `find_experts_in(topic="...")` to identify key authors in an area
3. **Citation analysis**: Use `get_citation_network(identifier="<DOI>", identifier_type="doi")` to see how papers connect
4. **Author profiles**: Use `get_author_profile(author_id)` for full publication history and metrics
5. **Trend analysis**: Use `analyze_trends(topic="...", timespan="2015-2025")` to track publication volume by year and classify whether a field is growing, declining, stable, or peaked

The server integrates well with Zotero MCP to compare Scopus discoveries against existing libraries.
""".strip()

mcp = FastMCP("Scopus", instructions=SERVER_INSTRUCTIONS)

_client = None
_client_lock = threading.Lock()


def _get_client():
    with _client_lock:
        if _client is None:
            raise RuntimeError(
                "Scopus client not initialised. Ensure main() completed startup."
            )
        return _client


def _register_tools() -> None:
    from scopus_mcp.tools.discovery import register_discovery_tools
    from scopus_mcp.tools.documents import register_document_tools
    from scopus_mcp.tools.citations import register_citation_tools
    from scopus_mcp.tools.authors import register_author_tools
    from scopus_mcp.tools.trends import register_trend_tools

    register_discovery_tools(mcp, _get_client)
    register_document_tools(mcp, _get_client)
    register_citation_tools(mcp, _get_client)
    register_author_tools(mcp, _get_client)
    register_trend_tools(mcp, _get_client)


def main() -> None:
    """Entry point called by the pyproject.toml script."""
    global _client

    from scopus_mcp.config import ConfigurationError, configure_logging, load_config
    from scopus_mcp.scopus.client import ScopusApiError, build_client

    try:
        config = load_config()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    configure_logging(config)

    try:
        client = build_client(config)
        client.request_json(
            "GET",
            "/content/search/scopus",
            params={"query": "scopus", "count": 1},
        )
    except ScopusApiError as exc:
        print(f"Scopus API error: {exc}", file=sys.stderr)
        sys.exit(1)

    with _client_lock:
        _client = client

    logger.info("Scopus client initialised successfully")
    _register_tools()
    mcp.run()


if __name__ == "__main__":
    main()

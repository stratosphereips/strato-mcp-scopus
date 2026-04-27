"""Scopus API client package."""

from scopus_mcp.scopus.client import ScopusApiError, ScopusClient, parse_citation_count

__all__ = ["ScopusClient", "ScopusApiError", "parse_citation_count"]

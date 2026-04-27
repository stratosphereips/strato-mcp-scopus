"""MCP tools for Scopus literature discovery."""

from scopus_mcp.scopus.client import parse_citation_count
from scopus_mcp.tools.schema import summarize_author, summarize_document

__all__ = ["summarize_document", "summarize_author", "parse_citation_count"]

_VALID_ID_TYPES = {"doi", "eid", "pii"}


def _resolve_id_field(identifier_type: str) -> str:
    """Normalise an identifier-type string into a Scopus path segment.

    Accepts any casing and falls back to ``"doi"`` for unknown types so callers
    never need to guard against bad input themselves.
    """
    normalised = identifier_type.lower()
    return normalised if normalised in _VALID_ID_TYPES else "doi"


def _tool_annotations(*, read_only: bool, destructive: bool = False):
    """Return MCP ToolAnnotations, or None if the MCP SDK is too old."""
    try:
        from mcp.types import ToolAnnotations
    except ImportError:
        return None
    return ToolAnnotations(
        readOnlyHint=read_only,
        destructiveHint=destructive,
        idempotentHint=read_only and not destructive,
        openWorldHint=True,
    )

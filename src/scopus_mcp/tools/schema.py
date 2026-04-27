"""Schema helpers for formatting Scopus results into agent-friendly summaries."""
from __future__ import annotations

from typing import Any


def summarize_document(doc: dict[str, Any]) -> dict[str, Any]:
    """Create a compact, agent-friendly summary of a Scopus document."""
    entry = doc.get("entry", doc)

    title = entry.get("dc:title")

    # STANDARD view returns dc:creator as a single primary-author string
    authors = []
    creator = entry.get("dc:creator")
    if creator:
        authors.append(str(creator))

    journal = entry.get("prism:publicationName")

    year = None
    cover_date = entry.get("prism:coverDate")
    if cover_date:
        year = str(cover_date)[:4]

    doi = entry.get("prism:doi")
    eid = entry.get("eid")

    citation_count = 0
    try:
        citation_count = int(entry.get("citedby-count", 0) or 0)
    except (ValueError, TypeError):
        pass

    # Abstract available in META_ABS / FULL views, not STANDARD
    abstract_snippet = None
    abstract_raw = entry.get("dc:description") or entry.get("abstract")
    if abstract_raw and isinstance(abstract_raw, str):
        abstract_snippet = abstract_raw[:200] + "..." if len(abstract_raw) > 200 else abstract_raw

    # Links use @ref (not @rel) in Scopus search results
    link = None
    for link_item in entry.get("link", []):
        if isinstance(link_item, dict) and link_item.get("@ref") == "self":
            link = link_item.get("@href")
            break

    return {
        "title": title,
        "authors": authors,
        "year": year,
        "journal": journal,
        "doi": doi,
        "eid": eid,
        "citation_count": citation_count,
        "abstract_snippet": abstract_snippet,
        "link": link,
    }


def summarize_author(author_data: dict[str, Any]) -> dict[str, Any]:
    """Create a compact, agent-friendly summary of a Scopus author."""
    # Handle both raw author-retrieval and author-search entry structures
    profile = author_data.get("author-profile", author_data)

    name = profile.get("preferred-name", {})
    if isinstance(name, dict):
        given = name.get("given-name", "")
        surname = name.get("surname", "")
        full_name = f"{given} {surname}".strip() or None
    else:
        full_name = profile.get("dc:title") or profile.get("preferred-name")

    # Current affiliation
    affiliation = None
    aff_current = profile.get("affiliation-current", {})
    if isinstance(aff_current, dict):
        affiliation = aff_current.get("affiliation-name")
    elif isinstance(aff_current, list) and aff_current:
        affiliation = aff_current[0].get("affilname") or aff_current[0].get("affiliation-name")

    # coredata block (author retrieval API)
    coredata = profile.get("coredata", {})

    citation_count = 0
    try:
        citation_count = int(coredata.get("citation-count", 0) or 0)
    except (ValueError, TypeError):
        pass

    h_index = 0
    try:
        h_index = int(coredata.get("h-index", 0) or 0)
    except (ValueError, TypeError):
        pass

    document_count = 0
    try:
        document_count = int(coredata.get("document-count", 0) or 0)
    except (ValueError, TypeError):
        pass

    # Author ID: strip AUTHOR_ID: prefix if present
    author_id = coredata.get("dc:identifier") or profile.get("dc:identifier")
    if isinstance(author_id, str) and ":" in author_id:
        author_id = author_id.split(":")[-1]

    return {
        "name": full_name,
        "affiliation": affiliation,
        "author_id": author_id,
        "document_count": document_count,
        "citation_count": citation_count,
        "h_index": h_index,
    }

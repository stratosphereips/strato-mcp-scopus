"""Schema helpers for formatting Scopus results into agent-friendly summaries."""
from __future__ import annotations

from typing import Any

from scopus_mcp.scopus.client import parse_citation_count


def summarize_document(doc: dict[str, Any]) -> dict[str, Any]:
    """Create a compact, agent-friendly summary of a Scopus document.

    Handles both response shapes:
    - Search entries (STANDARD view): fields at the top level of the entry.
    - Abstract retrieval (META/META_ABS view): fields nested under ``coredata``.
    """
    entry = doc.get("entry", doc) if isinstance(doc, dict) else doc
    coredata = entry.get("coredata", {}) if isinstance(entry, dict) else {}

    def pick(*keys: str) -> Any:
        for key in keys:
            if coredata.get(key) is not None:
                return coredata[key]
        for key in keys:
            if entry.get(key) is not None:
                return entry[key]
        return None

    title = pick("dc:title")

    # STANDARD view returns dc:creator as a single primary-author string;
    # META/META_ABS return a dict with an "author" list.
    authors: list[str] = []
    creator = pick("dc:creator")
    if isinstance(creator, dict):
        author_list = creator.get("author", [])
        if isinstance(author_list, list):
            for author in author_list:
                if not isinstance(author, dict):
                    continue
                preferred = author.get("preferred-name") or {}
                name = (
                    author.get("ce:indexed-name")
                    or preferred.get("ce:indexed-name")
                    or " ".join(
                        filter(
                            None,
                            [
                                author.get("ce:given-name"),
                                author.get("ce:surname"),
                            ],
                        )
                    )
                )
                if name:
                    authors.append(name)
    elif creator:
        authors.append(str(creator))

    journal = pick("prism:publicationName")

    year = None
    cover_date = pick("prism:coverDate")
    if cover_date:
        year = str(cover_date)[:4]

    doi = pick("prism:doi")
    eid = pick("eid")

    citation_count = parse_citation_count(
        coredata.get("citation-count")
        or coredata.get("citedby-count")
        or entry.get("citation-count")
        or entry.get("citedby-count")
    )

    # Abstract available in META_ABS / FULL views, not STANDARD / META.
    abstract_snippet = None
    abstract_raw = pick("dc:description")
    if not abstract_raw:
        item = entry.get("item") if isinstance(entry, dict) else None
        bibrecord = item.get("bibrecord", {}) if isinstance(item, dict) else {}
        head = bibrecord.get("head", {}) if isinstance(bibrecord, dict) else {}
        abstract_raw = head.get("abstracts")
    if abstract_raw and isinstance(abstract_raw, str):
        clean = abstract_raw.replace("<ce:para>", "\n").replace("</ce:para>", "")
        abstract_snippet = clean[:200] + "..." if len(clean) > 200 else clean

    # Search results use @ref="self"; abstract retrieval uses @rel="self".
    link = None
    for link_item in pick("link") or []:
        if isinstance(link_item, dict) and (
            link_item.get("@ref") == "self" or link_item.get("@rel") == "self"
        ):
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

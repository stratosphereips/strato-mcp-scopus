# Strato Scopus MCP

MCP server that connects Scopus to AI assistants for literature discovery. Tools are built around research workflows, not raw API endpoints. Works with Claude, Gemini CLI, OpenAI Codex, and any MCP-compatible client.

## What it does

### Find papers on a topic
`explore_topic` searches Scopus, sorts by citations, and returns titles, authors, journals, and abstract snippets.
```
"Find recent papers on transformer models for protein folding"
```

### Find who's working on a topic
`find_experts_in` scans recent high-impact papers and returns ranked author profiles with affiliations and citation metrics.
```
"Who are the key researchers in single-cell RNA sequencing?"
```

### Trace how an idea evolved
`get_citation_network` returns forward citations sorted by impact and flags highly cited follow-ups.
```
"What papers cite this one?"
```

### Check against your Zotero library
The agent calls Zotero MCP's `find_library_sources` first, then `explore_topic` to surface gaps. See [strato-mcp-zotero](https://github.com/stratosphereips/strato-mcp-zotero).
```
"Do I already have papers on diffusion models for drug discovery?"
```

### Track field growth over time
`analyze_trends` fetches publication counts year by year and classifies the trajectory as growing, declining, stable, or peaked.
```
"Has research on quantum computing in chemistry grown over the past decade?"
```

## Tools

**Discovery**
- `explore_topic(topic, years_back=2, limit=15, sort_by="cited_by_count")`
- `advanced_search(title, author, affiliation, keywords, year, doc_type)`

**Documents**
- `get_document_details(identifier, identifier_type="doi")`
- `find_similar_documents(identifier, identifier_type="doi", limit=5)`
- `compare_documents(identifiers, identifier_type="doi")`

**Citations**
- `get_citation_network(identifier, identifier_type="doi", max_citations=50)`
- `get_citation_metrics(identifiers, identifier_type="doi")`

**Authors**
- `find_experts_in(topic, field=None, limit=5, years_back=3)`
- `search_author(author_name, affiliation=None)`
- `get_author_profile(author_id, include_publications=False)`
- `compare_authors(author_ids)`

**Trends**
- `analyze_trends(topic, timespan="2015-2025")`

`identifier_type` accepts `"doi"`, `"eid"`, or `"pii"` throughout.

## Setup

**Get a Scopus API key** at https://dev.elsevier.com/myapikey.html. A free Elsevier developer account is enough for most features. Full-text access requires institutional credentials.

**Docker**

```bash
docker compose build
cp .env.example .env   # add your SCOPUS_API_KEY
chmod 600 .env
```

**Local**

```bash
uv sync
cp .env.example .env   # add your SCOPUS_API_KEY
uv run scopus-mcp
```

## Register with your AI assistant

<details>
<summary>Claude Desktop</summary>

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "scopus": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "--env-file", "/absolute/path/to/.env", "scopus-mcp:latest"]
    }
  }
}
```

Use the absolute path to `.env`. Claude Desktop launches Docker from an unknown working directory.

</details>

<details>
<summary>Claude Code</summary>

```bash
claude mcp add --transport stdio scopus -- \
  docker run --rm -i --env-file /absolute/path/to/.env scopus-mcp:latest
```

</details>

<details>
<summary>Gemini CLI</summary>

Edit `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "scopus": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "--env-file", "/absolute/path/to/.env", "scopus-mcp:latest"]
    }
  }
}
```

</details>

<details>
<summary>OpenAI Codex</summary>

Edit `~/.codex/config.toml`:

```toml
[[mcp_servers]]
name = "scopus"
command = "docker"
args = ["run", "--rm", "-i", "--env-file", "/absolute/path/to/.env", "scopus-mcp:latest"]
```

</details>

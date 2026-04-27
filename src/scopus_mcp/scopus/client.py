"""Authenticated Scopus Web API client."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from scopus_mcp.config import Config

logger = logging.getLogger(__name__)


def parse_citation_count(value: Any) -> int:
    """Parse a Scopus citation count field into an integer.

    Scopus returns citation counts in two distinct shapes depending on the endpoint:
    - Search results (STANDARD view): ``"citedby-count": "42"``  (plain string)
    - Abstract retrieval (META/META_ABS view): ``"citation-count": [{"$": "42"}]``

    This helper handles both forms, as well as bare integers and None.
    """
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    if isinstance(value, list):
        if not value:
            return 0
        first = value[0]
        if isinstance(first, dict):
            return parse_citation_count(first.get("$", 0))
        return parse_citation_count(first)
    return 0


@dataclass
class ScopusApiError(Exception):
    """Raised when the Scopus API returns an error."""

    message: str
    status_code: int | None = None
    response_body: str | None = None

    def __str__(self) -> str:
        if self.status_code is None:
            return self.message
        return f"{self.message} (HTTP {self.status_code})"


class ScopusClient:
    """Thin HTTP client for the Scopus Web API."""

    def __init__(self, config: Config, http_client: httpx.Client | None = None) -> None:
        self.config = config
        self._base_headers = {
            "Accept": "application/json",
            "X-ELS-APIKey": config.api_key,
            "X-ELS-Appid": config.api_key,  # Optional app identifier; falls back to API key when no separate ID is configured
        }
        if config.content_key:
            self._base_headers["X-ELS-ContentKey"] = config.content_key

        self._http = http_client or httpx.Client(
            base_url=config.api_base_url,
            timeout=60.0,  # Scopus can be slow
        )
        self._owns_http_client = http_client is None

    def close(self) -> None:
        """Close the HTTP client."""
        if self._owns_http_client:
            self._http.close()

    def request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[Any, httpx.Response]:
        """Perform an HTTP request and decode the JSON response when present."""
        request_headers = dict(self._base_headers)
        request_headers.update(headers or {})

        try:
            response = self._http.request(
                method=method,
                url=path,
                params=params,
                json=json_body,
                headers=request_headers or None,
            )
        except httpx.HTTPError as exc:
            raise ScopusApiError(f"Network error while calling Scopus API: {exc}") from exc

        if response.is_error:
            raise ScopusApiError(
                _format_error_message(response),
                status_code=response.status_code,
                response_body=response.text,
            )

        if response.status_code == 204 or not response.content:
            return None, response

        try:
            return response.json(), response
        except json.JSONDecodeError as exc:
            raise ScopusApiError(
                "Failed to decode JSON response from Scopus API.",
                status_code=response.status_code,
                response_body=response.text,
            ) from exc

    def get_with_pagination(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        """Make paginated requests and aggregate results."""
        all_results: list[dict[str, Any]] = []
        start = 0
        limit = min(self.config.default_limit, 100)

        while True:
            request_params = dict(params or {})
            request_params["start"] = start
            request_params["count"] = limit

            result, response = self.request_json("GET", path, params=request_params)

            if result is None:
                break

            # Extract results based on typical Scopus response structure
            hits = result.get("search-results", {}).get("entry", [])
            if not hits:
                break

            all_results.extend(hits)

            # Check if we've gotten all results
            total_results = int(
                result.get("search-results", {}).get("opensearch:totalResults", 0)
            )
            if max_results and len(all_results) >= max_results:
                all_results = all_results[:max_results]
                break

            if len(all_results) >= total_results:
                break

            start += limit

        return all_results


def build_client(config: Config) -> ScopusClient:
    """Return an authenticated Scopus Web API client."""
    logger.debug("Building Scopus client")
    return ScopusClient(config)


def _format_error_message(response: httpx.Response) -> str:
    """Format Scopus API error message."""
    reason = response.reason_phrase or "Unknown error"

    # Try to parse Scopus-specific error format
    try:
        error_data = response.json()
        service_error = error_data.get("service-error", {})
        status = service_error.get("status", {})
        status_text = status.get("statusText", "")

        if status_text:
            return f"Scopus API error: {status_text}"

        exceptions = service_error.get("exception", [])
        if isinstance(exceptions, list) and exceptions:
            exc_msg = exceptions[0].get("message", "")
            if exc_msg:
                return f"Scopus API error: {exc_msg}"
    except (json.JSONDecodeError, KeyError, IndexError):
        pass

    # Fallback to raw text
    if response.text:
        snippet = response.text.strip().replace("\n", " ")
        if len(snippet) > 200:
            snippet = snippet[:197] + "..."
        return f"Scopus API request failed: {reason}. {snippet}"

    return f"Scopus API request failed: {reason}."

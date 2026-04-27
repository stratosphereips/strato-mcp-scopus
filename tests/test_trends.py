"""Tests for Story 5 — Trend Analysis: analyze_trends."""
from __future__ import annotations

import datetime
import pytest
from unittest.mock import MagicMock

from scopus_mcp.scopus.client import ScopusApiError
from scopus_mcp.tools.trends import (
    _analyze_trends_impl,
    _classify_trend,
    _parse_timespan,
    register_trend_tools,
)
from tests.conftest import MockMCP, make_count_response


# ---------------------------------------------------------------------------
# _parse_timespan
# ---------------------------------------------------------------------------

class TestParseTimespan:
    def test_range_string(self):
        assert _parse_timespan("2014-2024") == (2014, 2024)

    def test_single_year_uses_current_as_end(self):
        start, end = _parse_timespan("2020")
        assert start == 2020
        assert end == datetime.date.today().year

    def test_leading_zeros_not_present_in_typical_input(self):
        start, end = _parse_timespan("2000-2010")
        assert start == 2000
        assert end == 2010


# ---------------------------------------------------------------------------
# _classify_trend
# ---------------------------------------------------------------------------

class TestClassifyTrend:
    def _counts(self, values):
        return [{"year": 2020 + i, "count": v} for i, v in enumerate(values)]

    def test_growing(self):
        assert _classify_trend(self._counts([10, 12, 15, 20, 30, 45])) == "growing"

    def test_declining(self):
        assert _classify_trend(self._counts([45, 35, 30, 20, 15, 10])) == "declining"

    def test_stable(self):
        assert _classify_trend(self._counts([20, 21, 19, 22, 20, 21])) == "stable"

    def test_peaked(self):
        # Rises then falls sharply — last value is <60% of peak
        assert _classify_trend(self._counts([10, 20, 80, 100, 30, 10])) == "peaked"

    def test_single_entry_insufficient(self):
        assert _classify_trend(self._counts([42])) == "insufficient data"

    def test_growing_from_zero_base(self):
        # first_half_avg is 0; second half is positive → growing
        assert _classify_trend(self._counts([0, 0, 0, 5, 10, 20])) == "growing"

    def test_all_zeros_stable(self):
        assert _classify_trend(self._counts([0, 0, 0, 0, 0, 0])) == "stable"


# ---------------------------------------------------------------------------
# _analyze_trends_impl
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_client():
    return MagicMock()


class TestAnalyzeTrendsImpl:
    def test_makes_one_request_per_year(self, mock_client):
        mock_client.request_json.return_value = (make_count_response(10), MagicMock())
        _analyze_trends_impl(mock_client, "test", "2020-2022")
        assert mock_client.request_json.call_count == 3  # 2020, 2021, 2022

    def test_yearly_counts_span_full_range(self, mock_client):
        mock_client.request_json.return_value = (make_count_response(10), MagicMock())
        result = _analyze_trends_impl(mock_client, "test", "2020-2022")
        years = [e["year"] for e in result["yearly_counts"]]
        assert years == [2020, 2021, 2022]

    def test_count_values_match_api_responses(self, mock_client):
        mock_client.request_json.return_value = (make_count_response(42), MagicMock())
        result = _analyze_trends_impl(mock_client, "test", "2020-2022")
        assert all(e["count"] == 42 for e in result["yearly_counts"])

    def test_total_publications_is_sum(self, mock_client):
        mock_client.request_json.return_value = (make_count_response(10), MagicMock())
        result = _analyze_trends_impl(mock_client, "test", "2020-2022")
        assert result["total_publications"] == 30

    def test_peak_year_identified(self, mock_client):
        counts = [5, 10, 50, 20, 8]
        mock_client.request_json.side_effect = [
            (make_count_response(c), MagicMock()) for c in counts
        ]
        result = _analyze_trends_impl(mock_client, "test", "2020-2024")
        assert result["peak_year"] == 2022  # index 2 → year 2020+2

    def test_notable_years_contains_peak_and_lowest(self, mock_client):
        counts = [5, 50, 20]
        mock_client.request_json.side_effect = [
            (make_count_response(c), MagicMock()) for c in counts
        ]
        result = _analyze_trends_impl(mock_client, "test", "2020-2022")
        assert result["notable_years"]["peak"]["count"] == 50
        assert result["notable_years"]["lowest"]["count"] == 5

    def test_growth_rate_calculated(self, mock_client):
        # first half [10, 10] avg=10, second half [20, 20] avg=20 → 100% growth
        counts = [10, 10, 20, 20]
        mock_client.request_json.side_effect = [
            (make_count_response(c), MagicMock()) for c in counts
        ]
        result = _analyze_trends_impl(mock_client, "test", "2020-2023")
        assert result["growth"]["growth_rate_pct"] == 100.0

    def test_growth_rate_none_when_first_half_is_zero(self, mock_client):
        counts = [0, 0, 5, 10]
        mock_client.request_json.side_effect = [
            (make_count_response(c), MagicMock()) for c in counts
        ]
        result = _analyze_trends_impl(mock_client, "test", "2020-2023")
        assert result["growth"]["growth_rate_pct"] is None

    def test_invalid_timespan_returns_error_without_api_calls(self, mock_client):
        result = _analyze_trends_impl(mock_client, "test", "2024-2020")
        assert "error" in result
        assert mock_client.request_json.call_count == 0

    def test_future_start_year_returns_error(self, mock_client):
        import datetime
        future = datetime.date.today().year + 5
        result = _analyze_trends_impl(mock_client, "test", f"{future}-{future + 2}")
        assert "error" in result
        assert mock_client.request_json.call_count == 0

    def test_malformed_timespan_returns_error(self, mock_client):
        result = _analyze_trends_impl(mock_client, "test", "not-a-year")
        assert "error" in result
        assert mock_client.request_json.call_count == 0

    def test_each_request_uses_count_1(self, mock_client):
        mock_client.request_json.return_value = (make_count_response(5), MagicMock())
        _analyze_trends_impl(mock_client, "test", "2020-2020")
        params = mock_client.request_json.call_args[1]["params"]
        assert params["count"] == 1

    def test_query_uses_pubyear_equals(self, mock_client):
        mock_client.request_json.return_value = (make_count_response(5), MagicMock())
        _analyze_trends_impl(mock_client, "cyber deception", "2023-2023")
        params = mock_client.request_json.call_args[1]["params"]
        assert "PUBYEAR = 2023" in params["query"]
        assert "TITLE-ABS-KEY(cyber deception)" in params["query"]

    def test_topic_in_result(self, mock_client):
        mock_client.request_json.return_value = (make_count_response(10), MagicMock())
        result = _analyze_trends_impl(mock_client, "cyber deception", "2020-2021")
        assert result["topic"] == "cyber deception"

    def test_end_year_capped_at_current_year(self, mock_client):
        mock_client.request_json.return_value = (make_count_response(0), MagicMock())
        future_end = datetime.date.today().year + 5
        result = _analyze_trends_impl(mock_client, "test", f"2020-{future_end}")
        last_year = result["yearly_counts"][-1]["year"]
        assert last_year == datetime.date.today().year

    def test_none_api_response_counted_as_zero(self, mock_client):
        mock_client.request_json.return_value = (None, MagicMock())
        result = _analyze_trends_impl(mock_client, "test", "2020-2020")
        assert result["yearly_counts"][0]["count"] == 0

    def test_trend_field_present_in_growth(self, mock_client):
        mock_client.request_json.return_value = (make_count_response(10), MagicMock())
        result = _analyze_trends_impl(mock_client, "test", "2020-2022")
        assert "trend" in result["growth"]
        assert result["growth"]["trend"] in {"growing", "declining", "stable", "peaked", "insufficient data"}


# ---------------------------------------------------------------------------
# analyze_trends MCP tool (registered)
# ---------------------------------------------------------------------------

class TestAnalyzeTrendsTool:
    def test_happy_path(self, mock_client):
        mcp = MockMCP()
        mock_client.request_json.return_value = (make_count_response(10), MagicMock())
        register_trend_tools(mcp, lambda: mock_client)
        result = mcp.tools["analyze_trends"](topic="cyber deception", timespan="2020-2022")
        assert result["topic"] == "cyber deception"
        assert "yearly_counts" in result
        assert "growth" in result

    def test_default_timespan_used_when_not_given(self, mock_client):
        mcp = MockMCP()
        mock_client.request_json.return_value = (make_count_response(10), MagicMock())
        register_trend_tools(mcp, lambda: mock_client)
        result = mcp.tools["analyze_trends"](topic="test")
        assert "yearly_counts" in result
        assert len(result["yearly_counts"]) > 0

    def test_api_error_returns_error_dict(self, mock_client):
        mcp = MockMCP()
        mock_client.request_json.side_effect = ScopusApiError("Quota exceeded", 429)
        register_trend_tools(mcp, lambda: mock_client)
        result = mcp.tools["analyze_trends"](topic="test", timespan="2020-2022")
        assert "error" in result

"""
test_fetcher.py — Unit tests for RFC list filtering and denylist behavior.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rfc_fetcher


def test_visible_rfcs_filters_hidden_entries(monkeypatch):
    monkeypatch.setattr(rfc_fetcher, "HIDDEN_RFC_NUMBERS", {12, 13})
    index = [
        {"rfcNumber": 11, "title": "Visible RFC"},
        {"rfcNumber": 12, "title": "Hidden RFC 12"},
        {"rfcNumber": 13, "title": "Hidden RFC 13"},
        {"rfcNumber": 14, "title": "Another Visible RFC"},
    ]

    visible = rfc_fetcher._visible_rfcs(index)

    assert [rfc["rfcNumber"] for rfc in visible] == [11, 14]


def test_get_rfc_list_excludes_hidden_rfcs_from_browse(monkeypatch):
    async def run_test():
        monkeypatch.setattr(rfc_fetcher, "HIDDEN_RFC_NUMBERS", {12, 13})
        monkeypatch.setattr(
            rfc_fetcher,
            "_load_index",
            lambda: [
                {"rfcNumber": 11, "title": "RFC Eleven"},
                {"rfcNumber": 12, "title": "RFC Twelve"},
                {"rfcNumber": 13, "title": "RFC Thirteen"},
                {"rfcNumber": 14, "title": "RFC Fourteen"},
            ],
        )

        result = await rfc_fetcher.get_rfc_list(page=1, limit=10)

        assert result["count"] == 2
        assert [rfc["rfcNumber"] for rfc in result["rfcs"]] == [14, 11]

    asyncio.run(run_test())


def test_get_rfc_list_search_does_not_return_hidden_rfcs(monkeypatch):
    async def run_test():
        monkeypatch.setattr(rfc_fetcher, "HIDDEN_RFC_NUMBERS", {12, 13})
        monkeypatch.setattr(
            rfc_fetcher,
            "_load_index",
            lambda: [
                {"rfcNumber": 11, "title": "RFC Eleven"},
                {"rfcNumber": 12, "title": "RFC Twelve"},
                {"rfcNumber": 13, "title": "RFC Thirteen"},
                {"rfcNumber": 120, "title": "RFC One Twenty"},
            ],
        )

        exact_hidden = await rfc_fetcher.get_rfc_list(page=1, limit=10, search="12")
        hidden_by_title = await rfc_fetcher.get_rfc_list(page=1, limit=10, search="thirteen")
        visible_partial = await rfc_fetcher.get_rfc_list(page=1, limit=10, search="120")

        assert exact_hidden["count"] == 1
        assert [rfc["rfcNumber"] for rfc in exact_hidden["rfcs"]] == [120]
        assert hidden_by_title["count"] == 0
        assert visible_partial["count"] == 1
        assert visible_partial["rfcs"][0]["rfcNumber"] == 120

    asyncio.run(run_test())
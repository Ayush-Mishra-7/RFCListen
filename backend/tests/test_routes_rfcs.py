import asyncio
import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes import rfcs


def test_parse_route_returns_504_on_timeout(monkeypatch):
    async def run_test():
        monkeypatch.setattr(
            rfcs,
            "_parse_rfc_with_timeout",
            lambda rfc_number, raw_text: (_ for _ in ()).throw(
                rfcs.RFCParseTimeoutError("timed out")
            ),
        )

        with pytest.raises(HTTPException) as exc_info:
            await rfcs._parse_rfc_or_raise(12, "text")

        assert exc_info.value.status_code == 504
        assert exc_info.value.detail == "timed out"

    asyncio.run(run_test())


def test_parse_route_returns_500_on_parser_error(monkeypatch):
    async def run_test():
        monkeypatch.setattr(
            rfcs,
            "_parse_rfc_with_timeout",
            lambda rfc_number, raw_text: (_ for _ in ()).throw(ValueError("boom")),
        )

        with pytest.raises(HTTPException) as exc_info:
            await rfcs._parse_rfc_or_raise(12, "text")

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Parser error: boom"

    asyncio.run(run_test())
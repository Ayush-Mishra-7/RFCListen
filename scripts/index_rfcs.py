#!/usr/bin/env python3
"""
scripts/index_rfcs.py — Utility script to pre-index a range of RFC numbers
into the local cache directory by fetching their text from rfc-editor.org.

Usage:
    python scripts/index_rfcs.py --start 1 --end 100 --delay 0.5

This is optional and only useful if you want to pre-warm the cache.
The backend fetches and caches RFCs on-demand by default.
"""
import argparse
import asyncio
import sys
from pathlib import Path

# Allow importing from backend/
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import httpx
from rfc_fetcher import get_rfc_text


async def index_range(start: int, end: int, delay: float):
    print(f"Indexing RFC {start}–{end} with {delay}s delay between requests.\n")
    for rfc_num in range(start, end + 1):
        try:
            text = await get_rfc_text(rfc_num)
            print(f"  ✓ RFC {rfc_num:>5} — {len(text):>7} chars")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                print(f"  ✗ RFC {rfc_num:>5} — not found (skipped)")
            else:
                print(f"  ! RFC {rfc_num:>5} — HTTP {e.response.status_code}")
        except Exception as e:
            print(f"  ! RFC {rfc_num:>5} — error: {e}")
        await asyncio.sleep(delay)
    print("\nDone.")


def main():
    parser = argparse.ArgumentParser(description="Pre-index RFC text files to local cache.")
    parser.add_argument("--start", type=int, default=1, help="First RFC number")
    parser.add_argument("--end",   type=int, default=100, help="Last RFC number")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay in seconds between requests")
    args = parser.parse_args()
    asyncio.run(index_range(args.start, args.end, args.delay))


if __name__ == "__main__":
    main()

import asyncio
import json
import os
from pathlib import Path

import sys
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BACKEND_DIR)

from rfc_fetcher import get_rfc_list

FRONTEND_DIR = Path(BACKEND_DIR).parent / "frontend"
OUTPUT_FILE = FRONTEND_DIR / "top-rfcs.json"

async def generate_static_json():
    print("Generating top 50 RFCs from the local RFC index cache...")
    try:
        # Fetch page 1, 50 limits (the default for the UI)
        data = await get_rfc_list(page=1, limit=50)
        
        # Ensure the frontend directory exists just in case
        FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
        
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        print(f"Successfully wrote {len(data.get('rfcs', []))} RFCs to {OUTPUT_FILE}")
        print("This file will be used by the frontend for instant loading.")
    except Exception as e:
        print(f"Error fetching RFC data: {e}")

if __name__ == "__main__":
    asyncio.run(generate_static_json())

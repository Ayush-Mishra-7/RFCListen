import asyncio
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

CACHE_DIR = Path(__file__).parent.parent / "cache"
INDEX_FILE = CACHE_DIR / "rfc_index.json"
XML_URL = "https://www.ietf.org/rfc/rfc-index.xml"

# Map old XML status to our UI standard
STATUS_MAP = {
    "PROPOSED STANDARD": "Proposed Standard",
    "DRAFT STANDARD": "Draft Standard",
    "INTERNET STANDARD": "Internet Standard",
    "BEST CURRENT PRACTICE": "Best Current Practice",
    "INFORMATIONAL": "Informational",
    "EXPERIMENTAL": "Experimental",
    "HISTORIC": "Historic",
    "UNKNOWN": "Unknown"
}

async def update_index():
    print(f"Downloading RFC index from {XML_URL}...")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    headers = {
        "User-Agent": "RFCListen/0.1 (https://github.com/rfclisten; educational project)"
    }
    async with httpx.AsyncClient(headers=headers, timeout=60.0) as client:
        response = await client.get(XML_URL)
        response.raise_for_status()
        xml_data = response.content

    print("Parsing XML data...")
    root = ET.fromstring(xml_data)
    
    # xmlns prefix
    ns = {'rfc': 'https://www.rfc-editor.org/rfc-index'}
    
    rfcs = []
    
    # Parse rfc elements
    for rfc_entry in root.findall('rfc:rfc-entry', ns):
        doc_id = rfc_entry.find('rfc:doc-id', ns).text
        if not doc_id.startswith('RFC'):
            continue
            
        rfc_num = int(doc_id[3:])
        title = rfc_entry.find('rfc:title', ns).text
        
        abstract_node = rfc_entry.find('rfc:abstract', ns)
        abstract = ""
        if abstract_node is not None:
             # Abstract can contain nested formatting
             abstract = "".join(abstract_node.itertext()).strip()
             
        status_node = rfc_entry.find('rfc:current-status', ns)
        status = STATUS_MAP.get(status_node.text, status_node.text) if status_node is not None else "Unknown"
        
        date_node = rfc_entry.find('rfc:date', ns)
        month = date_node.find('rfc:month', ns).text if date_node is not None and date_node.find('rfc:month', ns) is not None else "January"
        year = date_node.find('rfc:year', ns).text if date_node is not None else "1970"
        
        # approximate published date for sorting later if needed
        # Since we sort by rfc_number perfectly, we don't need exact ISO timestamps here,
        # but the UI expects something like YYYY-MM
        month_map = {"January": "01", "February": "02", "March": "03", "April": "04", 
                     "May": "05", "June": "06", "July": "07", "August": "08", 
                     "September": "09", "October": "10", "November": "11", "December": "12"}
        mm = month_map.get(month, "01")
        published = f"{year}-{mm}-01T00:00:00Z"
        
        rfcs.append({
            "rfcNumber": rfc_num,
            "name": f"rfc{rfc_num}",
            "title": title.strip() if title else "",
            "abstract": abstract,
            "status": status,
            "published": published
        })
        
    print(f"Parsed {len(rfcs)} RFCs.")
    
    # Sort chronologically by RFC number (Ascending) 
    # so the API can just reverse it for Descending
    rfcs.sort(key=lambda x: x["rfcNumber"])
    
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(rfcs, f, indent=2, ensure_ascii=False)
        
    print(f"Index successfully saved to {INDEX_FILE}")

if __name__ == "__main__":
    asyncio.run(update_index())

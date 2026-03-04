import httpx
import asyncio

async def test():
    url = "https://datatracker.ietf.org/api/v1/doc/document/"
    
    # Test sort newest to oldest
    params_desc = {
        "type": "rfc",
        "limit": 5,
        "format": "json",
        "order_by": "-time"
    }
    
    # Test sort oldest to newest
    params_asc = {
        "type": "rfc",
        "limit": 5,
        "format": "json",
        "order_by": "time"
    }
    
    # default order
    params_default = {
        "type": "rfc",
        "limit": 5,
        "format": "json",
    }
    
    async with httpx.AsyncClient() as client:
        res_desc = await client.get(url, params=params_desc)
        res_asc = await client.get(url, params=params_asc)
        res_default = await client.get(url, params=params_default)
        
        print("DESC by time:")
        for rfc in res_desc.json().get("objects", []):
            print(" ", rfc.get("name"), rfc.get("time"))
            
        print("\nASC by time:")
        for rfc in res_asc.json().get("objects", []):
            print(" ", rfc.get("name"), rfc.get("time"))
            
        print("\nDEFAULT:")
        for rfc in res_default.json().get("objects", []):
            print(" ", rfc.get("name"), rfc.get("time"))

asyncio.run(test())

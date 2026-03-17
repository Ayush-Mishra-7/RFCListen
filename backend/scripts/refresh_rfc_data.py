import asyncio

from generate_top_rfcs import generate_static_json
from update_rfc_index import update_index


async def refresh_rfc_data():
    print("Refreshing RFC index and frontend static list...")
    await update_index()
    await generate_static_json()
    print("RFC data refresh completed.")


if __name__ == "__main__":
    asyncio.run(refresh_rfc_data())
import asyncio
import sys
import traceback
sys.path.insert(0, '.')
from routes.rfcs import tts_voices

async def main():
    try:
        res = await tts_voices()
        print("Success!", res)
    except Exception as e:
        traceback.print_exc()

asyncio.run(main())

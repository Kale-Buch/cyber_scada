import asyncio
import aiohttp
import time

TARGET_URL = "http://127.0.0.1:5000/value"
CONNECTIONS = 2000
DURATION = 10

async def worker(session):
    while time.time() < end_time:
        try:
            async with session.get(TARGET_URL) as response:
                await response.text()
        except:
            pass

async def main():
    global end_time
    end_time = time.time() + DURATION
    async with aiohttp.ClientSession() as session:
        tasks = [worker(session) for _ in range(CONNECTIONS)]
        await asyncio.gather(*tasks)

asyncio.run(main())
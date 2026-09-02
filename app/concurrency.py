import asyncio

heavy_semaphore = asyncio.Semaphore(1)
light_semaphore = asyncio.Semaphore(2)

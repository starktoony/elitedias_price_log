import asyncio

from app.processes import process
from app import logger


async def run_in_loop():
    while True:
        try:
            await process()
        except Exception as e:
            logger.exception(e)


async def main():
    await run_in_loop()


if __name__ == "__main__":
    asyncio.run(main())

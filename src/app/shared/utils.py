import asyncio
import time
from datetime import datetime
from typing import Callable, TypeVar, Awaitable, ParamSpec
from app import logger


T_Rt = TypeVar("T_Rt")
T_Pr = ParamSpec("T_Pr")


def sleep_for(delay: float) -> None:
    logger.info(f"Sleep for {delay} seconds")
    time.sleep(delay)


def formated_datetime(
    now: datetime,
) -> str:
    formatted_date = now.strftime("%d/%m/%Y %H:%M:%S")
    return formatted_date


def split_list(lst: list, chunk_size: int) -> list[list]:
    """
    Split a list into smaller chunks of specified size

    Args:
        lst (list): Input list to split
        chunk_size (int): Size of each chunk

    Returns:
        list: List containing sublists of specified chunk size
    """
    return [lst[i : i + chunk_size] for i in range(0, len(lst), chunk_size)]


def afunc_retry(
    afunc: Callable[T_Pr, Awaitable[T_Rt]],
    max_retry: int = 3,
    sleep_interval: float = 1,
) -> Callable[T_Pr, Awaitable[T_Rt]]:
    async def wrapper(*args: T_Pr.args, **kwargs: T_Pr.kwargs) -> T_Rt:
        retry_time: int = 0
        while retry_time <= max_retry:
            try:
                return await afunc(*args, **kwargs)
            except Exception as e:
                logger.error(f"Retried: {retry_time} time(s). Error: {e}")
                if retry_time == max_retry:
                    raise e
            finally:
                retry_time += 1
                await asyncio.sleep(sleep_interval)

        raise

    return wrapper

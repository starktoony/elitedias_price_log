import asyncio
import httpx
import json

from typing import Final
from datetime import datetime

from app import config
from app.shared.paths import SRC_PATH

from .models import (
    AvailableGameResponse,
    ElitediasGameFields,
    ElitediasGameFieldsInfo,
)
from . import logger

ELITEDIAS_BASE_URL: Final[str] = "https://dev.api.elitedias.com"


async def _post_with_backoff(
    client: httpx.AsyncClient, url: str, **kwargs
) -> httpx.Response:
    delay = 1.0
    for attempt in range(5):
        res = await client.post(url, **kwargs)
        if res.status_code != 429:
            return res
        wait = delay * (2**attempt)
        logger.warning(f"Rate limited (429) on {url}, retrying in {wait:.1f}s")
        await asyncio.sleep(wait)
    return res


class ElitediasAPIClient:
    def __init__(self) -> None:
        self.headers = {
            "Origin": config.ORIGIN,
            "Content-Type": "application/json",
            "User-Agent": "PostmanRuntime/7.44.1",
        }
        self.base_url = ELITEDIAS_BASE_URL

    async def get_available_games(self) -> AvailableGameResponse:
        async with httpx.AsyncClient(headers=self.headers) as client:
            res = await _post_with_backoff(
                client,
                f"{self.base_url}/elitedias_games_data",
                json={"api_key": config.ALITEDIAS_API_KEY},
                timeout=60,
            )
            try:
                res.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.exception(e)
                logger.info(res.text)
                raise
            return AvailableGameResponse.model_validate(res.json())

    async def get_denominations(self, game: str) -> dict[str, float]:
        async with httpx.AsyncClient(headers=self.headers) as client:
            res = await client.post(
                f"{self.base_url}/elitedias_api_denominations",
                json={"api_key": config.ALITEDIAS_API_KEY, "game": game},
                timeout=60,
            )
            try:
                res.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.exception(e)
                logger.info(res.text)
                raise
            return res.json()

    async def get_elitedias_game_fields(self, game: str) -> ElitediasGameFields:
        _empty = ElitediasGameFields(
            code="200", info=ElitediasGameFieldsInfo(fields=[], notes="")
        )
        cached_data = {}
        with open(SRC_PATH / "data" / "game_notes.json") as f:
            cached_data = json.load(f)
            if game in cached_data:
                return ElitediasGameFields(
                    code="200",
                    info=ElitediasGameFieldsInfo(fields=[], notes=cached_data[game]),
                )
        try:
            async with httpx.AsyncClient(headers=self.headers) as client:
                res = await client.post(
                    f"{self.base_url}/elitedias_game_fields",
                    json={"api_key": config.ALITEDIAS_API_KEY, "game": game},
                    timeout=60,
                )
                res.raise_for_status()
                model_response = ElitediasGameFields.model_validate(res.json())
                cached_data[game] = model_response.info.notes
                with open(SRC_PATH / "data" / "game_notes.json", "w") as f:
                    json.dump(cached_data, f, indent=4)
                return model_response
        except Exception as e:
            logger.error(f"Failed to fetch game fields for {game}: {e}")
            return _empty


elitedias_api_client = ElitediasAPIClient()

import asyncio
import httpx
import json

from typing import Final

from datetime import datetime, timedelta

from app import config
from app.shared.paths import SRC_PATH
from app.shared.cache_store import ModelKeyValueStore, CacheData


from .models import (
    AvailableGameResponse,
    ElitediasGameFields,
    ElitediasGameFieldsInfo,
)
from . import logger

ELITEDIAS_BASE_URL: Final[str] = "https://dev.api.elitedias.com"


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
            res = await client.post(
                f"{self.base_url}/elitedias_games_available",
                json={
                    "api_key": config.ALITEDIAS_API_KEY,
                },
                timeout=60,
            )

            try:
                res.raise_for_status()

            except httpx.HTTPStatusError as e:
                logger.exception(e)
                logger.info(res.text)
                res.raise_for_status()

            return AvailableGameResponse.model_validate(res.json())

    async def get_denominations(self, game: str) -> dict[str, float]:
        store = ModelKeyValueStore(
            "denominations",
            SRC_PATH / "data" / "store",
            CacheData[dict[str, float]],
        )

        cached_data = store.get(game)
        if cached_data and cached_data.is_valid():
            return cached_data.data

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
                res.raise_for_status()

            response_data = res.json()

            cached_data = CacheData[dict[str, float]].model_validate(
                {
                    "date": datetime.now(),
                    "valid": timedelta(days=config.CACHE_VALID),
                    "data": response_data,
                }
            )
            store.set(game, cached_data)
            return response_data

    async def get_elitedias_game_fields(self, game: str) -> ElitediasGameFields:
        cached_data = {}
        with open(SRC_PATH / "data" / "game_notes.json") as f:
            cached_data = json.load(f)
            if game in cached_data:
                return ElitediasGameFields(
                    code="200",
                    info=ElitediasGameFieldsInfo(fields=[], notes=cached_data[game]),
                )
        async with httpx.AsyncClient(headers=self.headers) as client:
            res = await client.post(
                f"{self.base_url}/elitedias_game_fields",
                json={"api_key": config.ALITEDIAS_API_KEY, "game": game},
                timeout=60,
            )

            try:
                res.raise_for_status()

            except httpx.HTTPStatusError as e:
                logger.exception(e)
                logger.info(res.text)
                res.raise_for_status()

            await asyncio.sleep(10)

            model_response = ElitediasGameFields.model_validate(res.json())

            cached_data[game] = model_response.info.notes
            with open(SRC_PATH / "data" / "game_notes.json", "w") as f:
                json.dump(cached_data, f, indent=4)

            return model_response


elitedias_api_client = ElitediasAPIClient()

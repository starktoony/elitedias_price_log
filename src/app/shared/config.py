import os

from dotenv import load_dotenv

from pydantic import BaseModel


class Config(BaseModel):
    # Keys
    KEYS_PATH: str

    # Sheets
    SHEET_ID: str
    SHEET_NAME: str
    SHEET_DATA_NAME: str

    # Plsbuy credentials
    ALITEDIAS_API_KEY: str

    # Process batch size
    PROCESS_BATCH_SIZE: int

    # Relax time each batch process
    RELAX_TIME_EACH_BATCH: float

    # Relax time each round in second
    RELAX_TIME_EACH_ROUND: str

    # Relax time cell
    RELAX_TIME_CELL: str

    # Start index for data sheet
    SHEET_DATA_START_INDEX: int = 3

    # Origin
    ORIGIN: str = "sosanhsach.io"

    # Cache valid duration
    CACHE_VALID: int = 7  # days

    @staticmethod
    def from_env(dotenv_path: str = "settings.env") -> "Config":
        load_dotenv(dotenv_path)
        return Config.model_validate(os.environ)

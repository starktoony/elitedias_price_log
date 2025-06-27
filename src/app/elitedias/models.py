from pydantic import BaseModel


class AvailableGameResponse(BaseModel):
    code: str
    games: list[str]


class ElitediasGameFieldsInfo(BaseModel):
    fields: list[str]
    notes: str


class ElitediasGameFields(BaseModel):
    code: str
    info: ElitediasGameFieldsInfo


class FriElidiasGame(BaseModel):
    game: str
    denominations: dict[str, str | float]
    notes: str
    currency: str = "SGD"

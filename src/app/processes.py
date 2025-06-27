import asyncio


from datetime import datetime

from .elitedias.api import elitedias_api_client
from .elitedias.models import FriElidiasGame, ElitediasGameFields
from .sheet.models import BatchCellUpdatePayload, RowModel, DataRow
from .sheet.enums import CheckType
from .shared.utils import split_list, sleep_for, formated_datetime
from .shared.decorators import retry_on_fail

from app import logger, config


def batch_update_price(
    to_be_updated_row_models: list[RowModel],
):
    update_dict: dict[str, dict[str, list[BatchCellUpdatePayload]]] = {}
    for row_model in to_be_updated_row_models:
        if row_model.ID_SHEET and row_model.SHEET and row_model.CELL:
            if row_model.ID_SHEET not in update_dict:
                update_dict[row_model.ID_SHEET] = {}
                update_dict[row_model.ID_SHEET][row_model.SHEET] = [
                    BatchCellUpdatePayload[str](
                        cell=row_model.CELL,
                        value=row_model.PRICE if row_model.PRICE else "",
                    )
                ]

            else:
                if row_model.SHEET not in update_dict[row_model.ID_SHEET]:
                    update_dict[row_model.ID_SHEET][row_model.SHEET] = [
                        BatchCellUpdatePayload[str](
                            cell=row_model.CELL,
                            value=row_model.PRICE if row_model.PRICE else "",
                        )
                    ]
                else:
                    update_dict[row_model.ID_SHEET][row_model.SHEET].append(
                        BatchCellUpdatePayload[str](
                            cell=row_model.CELL,
                            value=row_model.PRICE if row_model.PRICE else "",
                        )
                    )

    for sheet_id, sheet_names in update_dict.items():
        for sheet_name, update_batch in sheet_names.items():
            RowModel.free_style_batch_update(
                sheet_id=sheet_id, sheet_name=sheet_name, update_payloads=update_batch
            )


@retry_on_fail(max_retries=5, sleep_interval=10)
def batch_process(
    game_dict: dict[str, FriElidiasGame],
    indexes: list[int],
):
    # Get all run row from sheet
    logger.info(f"Get all run row from sheet: {indexes}")
    row_models = RowModel.batch_get(
        sheet_id=config.SHEET_ID,
        sheet_name=config.SHEET_NAME,
        indexes=indexes,
    )

    to_be_updated_row_models: list[RowModel] = []

    # Process for each row model

    logger.info("Processing")
    for row_model in row_models:
        if (
            row_model.GAME_NAME in game_dict
            and row_model.DENOMINATION in game_dict[row_model.GAME_NAME].denominations
        ):
            row_model.PRICE = str(
                game_dict[row_model.GAME_NAME].denominations[row_model.DENOMINATION]
            )
            row_model.GAME_NOTE = game_dict[row_model.GAME_NAME].notes
            row_model.CURRENCY = game_dict[row_model.GAME_NAME].currency
            row_model.NOTE = f"{formated_datetime(datetime.now())} Cập nhật thành công"

        else:
            row_model.NOTE = f"{formated_datetime(datetime.now())} GAME_NAME: {row_model.GAME_NAME} hoặc DENOMINATION: {row_model.DENOMINATION} không hợp lệ"
            row_model.PRICE = ""

        if row_model.FILL_IN == CheckType.RUN.value:
            to_be_updated_row_models.append(row_model)

    logger.info("Price sheet updating")
    batch_update_price(to_be_updated_row_models)

    logger.info("Sheet updating")
    RowModel.batch_update(
        sheet_id=config.SHEET_ID,
        sheet_name=config.SHEET_NAME,
        list_object=row_models,
    )

    sleep_for(config.RELAX_TIME_EACH_BATCH)


def update_sheet_data(game_dict: dict[str, FriElidiasGame]):
    data_rows: list[DataRow] = []
    for _, game in game_dict.items():
        for denomination, price in game.denominations.items():
            data_rows.append(
                DataRow(
                    sheet_id=config.SHEET_ID,
                    sheet_name=config.SHEET_DATA_NAME,
                    index=len(data_rows) + config.SHEET_DATA_START_INDEX,
                    STT=len(data_rows) + 1,
                    Game=game.game,
                    Denomination=denomination,
                    Price=str(price),
                    Update_at=formated_datetime(datetime.now()),
                )
            )

    DataRow.batch_update(
        sheet_id=config.SHEET_ID,
        sheet_name=config.SHEET_DATA_NAME,
        list_object=data_rows,
    )


async def get_game_dict() -> dict[str, FriElidiasGame]:
    game_dict: dict[str, FriElidiasGame] = {}

    logger.info("## Getting game")
    games: list[str] = (await elitedias_api_client.get_available_games()).games

    logger.info("## Getting denominations")
    __tasks = []
    for game in games:
        __tasks.append(elitedias_api_client.get_denominations(game))

    denominations = await asyncio.gather(*__tasks)

    logger.info("## Getting game fields")
    __tasks = []
    for game in games:
        __tasks.append(elitedias_api_client.get_elitedias_game_fields(game))

    game_fields_responses: list[ElitediasGameFields] = await asyncio.gather(*__tasks)

    for i, game in enumerate(games):
        game_dict[game] = FriElidiasGame(
            game=game,
            notes=game_fields_responses[i].info.notes,
            denominations=denominations[i],
        )

    return game_dict


async def process():
    logger.info("# Getting Elitedias games")

    game_dict = await get_game_dict()

    logger.info("Updating Sheet data")
    update_sheet_data(game_dict)

    logger.info(f"## Total game: {len(game_dict)}")

    # Get run_indexes from sheet
    run_indexes = RowModel.get_run_indexes(
        sheet_id=config.SHEET_ID,
        sheet_name=config.SHEET_NAME,
        col_index=2,
    )

    for batch_indexes in split_list(run_indexes, config.PROCESS_BATCH_SIZE):
        batch_process(
            game_dict=game_dict,
            indexes=batch_indexes,
        )

    str_relax_time = RowModel.get_cell_value(
        sheet_id=config.SHEET_ID,
        sheet_name=config.SHEET_NAME,
        cell=config.RELAX_TIME_CELL,
    )

    sleep_for(float(str_relax_time) if str_relax_time else 10)

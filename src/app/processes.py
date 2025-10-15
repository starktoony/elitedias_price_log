import asyncio


from datetime import datetime
from httpx import HTTPStatusError

from gspread.worksheet import ValueRange
from gspread.utils import rowcol_to_a1

from .elitedias.api import elitedias_api_client
from .elitedias.models import FriElidiasGame, ElitediasGameFields
from .sheet.models import BatchCellUpdatePayload, RowModel, DataRow
from .sheet.enums import CheckType
from .shared.utils import split_list, sleep_for, formated_datetime
from .shared.decorators import retry_on_fail

from app import logger, config
from app.sheet.utils import fri_a1_range_to_grid_range


def find_cell_to_update(row_models: list[RowModel]) -> dict[str, str]:
    mapping_dict: dict[str, str] = {}

    sheet_get_batch_dict: dict[str, dict[str, list[str]]] = {}

    for row_model in row_models:
        if (
            row_model.FILL_IN
            and row_model.ID_SHEET
            and row_model.SHEET
            and row_model.COL_NOTE
            and row_model.CODE
            and row_model.COL_CODE
        ):
            range_code = f"{row_model.COL_CODE}:{row_model.COL_CODE}"
            if row_model.ID_SHEET not in sheet_get_batch_dict:
                sheet_get_batch_dict[row_model.ID_SHEET] = {}
                sheet_get_batch_dict[row_model.ID_SHEET][row_model.SHEET] = [range_code]
            else:
                if row_model.SHEET not in sheet_get_batch_dict[row_model.ID_SHEET]:
                    sheet_get_batch_dict[row_model.ID_SHEET][row_model.SHEET] = [
                        range_code
                    ]
                else:
                    sheet_get_batch_dict[row_model.ID_SHEET][row_model.SHEET].append(
                        range_code
                    )
    # dict[sheet_id, dict[sheet_name, range, value_range]]
    sheet_get_batch_result_dict: dict[str, dict[str, dict[str, ValueRange]]] = {}

    for sheet_id, sheet_names in sheet_get_batch_dict.items():
        for sheet_name, get_batch in sheet_names.items():
            _get_batch_resutl: list[ValueRange] = RowModel.get_worksheet(
                sheet_id=sheet_id, sheet_name=sheet_name
            ).batch_get(ranges=get_batch)
            for i, range in enumerate(_get_batch_resutl):
                if sheet_id not in sheet_get_batch_result_dict:
                    sheet_get_batch_result_dict[sheet_id] = {}
                if sheet_name not in sheet_get_batch_result_dict[sheet_id]:
                    sheet_get_batch_result_dict[sheet_id][sheet_name] = {}
                if (
                    get_batch[i]
                    not in sheet_get_batch_result_dict[sheet_id][sheet_name]
                ):
                    sheet_get_batch_result_dict[sheet_id][sheet_name][get_batch[i]] = (
                        range
                    )

    for row_model in row_models:
        if (
            row_model.ID_SHEET
            and row_model.SHEET
            and row_model.COL_NOTE
            and row_model.CODE
            and row_model.COL_CODE
        ):
            # Convert to A1 notation
            range_code = f"{row_model.COL_CODE}:{row_model.COL_CODE}"
            range_note = f"{row_model.COL_NOTE}:{row_model.COL_NOTE}"

            _codes_grid = sheet_get_batch_result_dict[row_model.ID_SHEET][
                row_model.SHEET
            ][range_code]

            code_grid_range = fri_a1_range_to_grid_range(range_code)
            note_grid_range = fri_a1_range_to_grid_range(range_note)
            for i, code_row in enumerate(_codes_grid):
                for j, code_col in enumerate(code_row):
                    if (
                        isinstance(code_col, str)
                        and row_model.CODE.strip() == code_col.strip()
                    ):
                        target_row_index = i + 1 + code_grid_range.startRowIndex
                        target_col_index = j + 1 + note_grid_range.startColumnIndex
                        mapping_dict[str(row_model.index)] = rowcol_to_a1(
                            target_row_index, target_col_index
                        )

    return mapping_dict


def batch_update_price(
    to_be_updated_row_models: list[RowModel],
):
    update_dict: dict[str, dict[str, list[BatchCellUpdatePayload]]] = {}

    update_cell_mapping = find_cell_to_update(to_be_updated_row_models)

    for row_model in to_be_updated_row_models:
        if row_model.ID_SHEET and row_model.SHEET and row_model.COL_NOTE:
            if row_model.ID_SHEET not in update_dict:
                update_dict[row_model.ID_SHEET] = {}

            if row_model.SHEET not in update_dict[row_model.ID_SHEET]:
                update_dict[row_model.ID_SHEET][row_model.SHEET] = []

            if str(row_model.index) in update_cell_mapping:
                update_dict[row_model.ID_SHEET][row_model.SHEET].append(
                    BatchCellUpdatePayload[str](
                        cell=update_cell_mapping[str(row_model.index)],
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
    denominations = []
    for game in games:
        logger.info(f"Getting denominations for {game}")
        try:
            game_denominations = await elitedias_api_client.get_denominations(game)
            denominations.append(game_denominations)
        except HTTPStatusError as e:
            logger.error(f"Error getting denominations for {game}: {e}")
            denominations.append({})

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

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Run the main loop:**
```bash
cd src && uv run python main.py
```

**Run ad-hoc test scripts:**
```bash
cd src && uv run python test.py
```

**Add/sync dependencies:**
```bash
uv sync
```

There is no test suite — `src/test.py` is a scratch file for manual API testing.

## Environment Setup

- Config is loaded from `settings.env` at the repo root via `python-dotenv`.
- Google Sheets auth uses a service account key file; its path is set by `KEYS_PATH` in `settings.env` (defaults to `keys.json` at the repo root).
- All scripts must be run from `src/` (or with `src/` on the path) because imports are relative to that directory.

## Architecture

This is a price-sync automation script that periodically:
1. Fetches game lists and denominations from the Elitedias REST API.
2. Writes all game/denomination/price data to a "Data" sheet.
3. Reads rows marked with `CHECK = "1"` from a "Log" sheet, looks up the matching price, and writes it back — along with a status note and optional cross-sheet price update.
4. Sleeps for the interval stored in a configurable sheet cell (`RELAX_TIME_CELL`), then repeats forever.

### Entry point & orchestration

`src/main.py` → `src/app/processes.py::process()` (the main async loop body).

`process()` calls in order:
- `get_game_dict()` — fetches available games, denominations (with file cache), and game notes (with JSON cache).
- `update_sheet_data()` — bulk-writes all games/denominations to the Data sheet.
- `RowModel.get_run_indexes()` — finds rows where column B = "1".
- `batch_process()` (one call per chunk) — reads row data, fills in prices, and writes back.

### Sheet model layer (`src/app/sheet/models.py`)

`ColSheetModel` is the base class for all sheet row models. It uses **Pydantic field metadata** to declare sheet column mappings:

```python
PRICE: Annotated[str | None, {COL_META: "G", IS_UPDATE_META: True}] = None
```

- `COL_META` — the sheet column letter this field maps to.
- `IS_UPDATE_META: True` — field is written back on update.
- `IS_NOTE_META: True` — field is used as the error/status note column.

Class methods (`batch_get`, `batch_update`, `free_style_batch_update`, etc.) use these annotations to construct A1 notation ranges for the gspread API automatically.

`RowModel` maps the main log sheet (columns B–P). `DataRow` maps the data sheet (columns A–E).

### Cross-sheet price updates (`find_cell_to_update`)

When a `RowModel` row has `FILL_IN = "1"` plus `ID_SHEET`, `SHEET`, `COL_CODE`, `CODE`, and `COL_NOTE` filled in, the script also updates a cell in a *different* Google Sheet. `find_cell_to_update()` scans the target sheet's code column to locate the matching row, then `batch_update_price()` writes the price there.

### Caching

- **Denominations**: persisted as JSON in `src/data/store/denominations.json` via `ModelKeyValueStore`. Cache validity is controlled by `CACHE_VALID` in config (default 1 day).
- **Game notes**: persisted in `src/data/game_notes.json`. Checked before every API call; updated after a live fetch.

### API client (`src/app/elitedias/api.py`)

`ElitediasAPIClient` — singleton `elitedias_api_client`. Uses `httpx` async client. All requests POST to `https://dev.api.elitedias.com` with `api_key` in the JSON body. The `Origin` header is configurable via `ORIGIN` in config (defaults to `"sosanhsach.io"`).

### Retry behaviour

`@retry_on_fail(max_retries, sleep_interval)` in `src/app/shared/decorators.py` wraps synchronous callables. It is applied to all sheet I/O methods and `batch_process`. The top-level loop in `main.py` catches and logs any unhandled exceptions so the process never exits.

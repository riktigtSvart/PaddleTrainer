import os
from pathlib import Path
import sqlite3

from app.pft_engine.storage.schema import (
    initialize_schema,
)


ENV_DATABASE_PATH = (
    "PADDLETRAINER_PHYSIOLOGY_DB"
)


def default_database_path() -> Path:
    configured = os.getenv(
        ENV_DATABASE_PATH
    )

    if configured:
        return Path(
            configured
        ).expanduser()

    return (
        Path.home()
        / ".app.pft_engine"
        / "pft.sqlite3"
    )


def open_database(
    path: str | Path | None = None,
) -> sqlite3.Connection:

    if path is None:
        database_path = (
            default_database_path()
        )
    else:
        database_path = Path(path)

    if str(database_path) != ":memory:":
        database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    connection = sqlite3.connect(
        str(database_path)
    )

    connection.row_factory = (
        sqlite3.Row
    )

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    initialize_schema(
        connection
    )

    return connection
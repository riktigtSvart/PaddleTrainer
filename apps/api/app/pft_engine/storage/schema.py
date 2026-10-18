import sqlite3


DB_SCHEMA_VERSION = 2


SESSION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pft_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    source_sha256 TEXT NOT NULL UNIQUE,
    source_filename TEXT NOT NULL,

    started_at TEXT NOT NULL,

    protocol_name TEXT NOT NULL,
    protocol_version TEXT NOT NULL,

    output_schema_version TEXT NOT NULL,
    processor_version TEXT NOT NULL,

    quality_grade TEXT NOT NULL,

    result_json TEXT NOT NULL,

    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_pft_sessions_started_at
ON pft_sessions(started_at);

CREATE INDEX IF NOT EXISTS ix_pft_sessions_protocol
ON pft_sessions(protocol_name, protocol_version);
"""


SAMPLE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pft_session_samples (
    session_id INTEGER NOT NULL,
    sample_index INTEGER NOT NULL,

    elapsed_s REAL NOT NULL,

    hr_bpm REAL,
    power_w REAL,
    speed_mps REAL,
    cadence_rpm REAL,
    distance_m REAL,

    PRIMARY KEY (
        session_id,
        sample_index
    ),

    FOREIGN KEY (session_id)
        REFERENCES pft_sessions(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_pft_session_samples_elapsed
ON pft_session_samples(
    session_id,
    elapsed_s
);
"""


def initialize_schema(
    connection: sqlite3.Connection,
) -> None:
    current_version = connection.execute(
        "PRAGMA user_version"
    ).fetchone()[0]

    if current_version > DB_SCHEMA_VERSION:
        raise RuntimeError(
            "Database schema is newer than this "
            "PaddleTrainerPhysiology version supports: "
            f"{current_version} > {DB_SCHEMA_VERSION}"
        )

    if current_version == 0:
        connection.executescript(
            SESSION_SCHEMA_SQL
        )

        connection.executescript(
            SAMPLE_SCHEMA_SQL
        )

        connection.execute(
            "PRAGMA user_version = 2"
        )

        connection.commit()
        return

    if current_version == 1:
        connection.executescript(
            SAMPLE_SCHEMA_SQL
        )

        connection.execute(
            "PRAGMA user_version = 2"
        )

        connection.commit()
        return

    if current_version == DB_SCHEMA_VERSION:
        connection.executescript(
            SESSION_SCHEMA_SQL
        )

        connection.executescript(
            SAMPLE_SCHEMA_SQL
        )

        connection.commit()
        return

    raise RuntimeError(
        "Unsupported database schema migration path: "
        f"{current_version} -> "
        f"{DB_SCHEMA_VERSION}"
    )
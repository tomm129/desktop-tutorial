"""DuckDB: migrations versionadas, upsert/dedup, backup diário.

Interface usada pelos demais módulos:
    db.query(sql, params) -> pd.DataFrame
    db.execute(sql, params)
    db.insert_dataframe(df, table, if_exists="append")
    db.upsert_dataframe(df, table, key_columns) -> int inseridos (anti-join)
    db.insert_candles(df) -> int inseridos (dedup por symbol/timeframe/timestamp)
    db.get_candle_count(symbol, timeframe) -> int
    db.get_last_candle_timestamp(symbol, timeframe) -> datetime UTC | None
    db.backup() / db.close()
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd
import structlog

from crypto_bot.config import SETTINGS

logger = structlog.get_logger(__name__)

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"

CANDLE_COLUMNS = ["symbol", "timeframe", "timestamp", "open", "high", "low", "close", "volume"]


def _quote(col: str) -> str:
    return f'"{col}"'


class Database:
    """Wrapper DuckDB com conexão lazy e migrations automáticas."""

    def __init__(self, path: str | None = None, backup_dir: str | None = None) -> None:
        self.path = Path(path or SETTINGS.database.path)
        self.backup_dir = Path(backup_dir or SETTINGS.database.backup_dir)
        self._con: Optional[duckdb.DuckDBPyConnection] = None

    @property
    def con(self) -> duckdb.DuckDBPyConnection:
        if self._con is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._con = duckdb.connect(str(self.path))
            self._migrate()
        return self._con

    # ------------------------------------------------------------------ #
    # Migrations
    # ------------------------------------------------------------------ #

    def _migrate(self) -> None:
        """Aplica os arquivos *.sql de crypto_bot/schema em ordem, uma única vez cada."""
        assert self._con is not None
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename VARCHAR PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        applied = {
            row[0]
            for row in self._con.execute("SELECT filename FROM schema_migrations").fetchall()
        }
        for sql_file in sorted(SCHEMA_DIR.glob("*.sql")):
            if sql_file.name in applied:
                continue
            self._con.execute(sql_file.read_text())
            self._con.execute(
                "INSERT INTO schema_migrations (filename) VALUES (?)", [sql_file.name]
            )
            logger.info("database.migration.applied", filename=sql_file.name)

    # ------------------------------------------------------------------ #
    # Helpers genéricos
    # ------------------------------------------------------------------ #

    def query(self, sql: str, params: list | None = None) -> pd.DataFrame:
        return self.con.execute(sql, params or []).fetchdf()

    def execute(self, sql: str, params: list | None = None) -> None:
        self.con.execute(sql, params or [])

    def insert_dataframe(self, df: pd.DataFrame, table: str, if_exists: str = "append") -> None:
        """Insert simples (sem dedup). Prefira upsert_dataframe para tabelas com PK."""
        if df.empty:
            return
        cols = ", ".join(_quote(c) for c in df.columns)
        self.con.register("_df_insert", df)
        try:
            self.con.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM _df_insert")
        finally:
            self.con.unregister("_df_insert")

    def upsert_dataframe(self, df: pd.DataFrame, table: str, key_columns: list[str]) -> int:
        """Insere apenas linhas cujas chaves ainda não existem (anti-join). Retorna nº inserido."""
        if df.empty:
            return 0
        cols = ", ".join(_quote(c) for c in df.columns)
        join = " AND ".join(f"t.{_quote(k)} = d.{_quote(k)}" for k in key_columns)
        self.con.register("_df_upsert", df)
        try:
            result = self.con.execute(
                f"""
                INSERT INTO {table} ({cols})
                SELECT {cols} FROM _df_upsert d
                WHERE NOT EXISTS (SELECT 1 FROM {table} t WHERE {join})
                """
            ).fetchone()
        finally:
            self.con.unregister("_df_upsert")
        return int(result[0]) if result else 0

    # ------------------------------------------------------------------ #
    # Candles
    # ------------------------------------------------------------------ #

    def insert_candles(self, df: pd.DataFrame) -> int:
        """Insere candles com dedup por (symbol, timeframe, timestamp). Retorna nº inserido."""
        if df.empty:
            return 0
        df = df[CANDLE_COLUMNS].copy()
        return self.upsert_dataframe(df, "candles", ["symbol", "timeframe", "timestamp"])

    def get_candle_count(self, symbol: str, timeframe: str) -> int:
        result = self.con.execute(
            "SELECT COUNT(*) FROM candles WHERE symbol = ? AND timeframe = ?",
            [symbol, timeframe],
        ).fetchone()
        return int(result[0]) if result else 0

    def get_last_candle_timestamp(self, symbol: str, timeframe: str) -> Optional[datetime]:
        result = self.con.execute(
            "SELECT max(timestamp) FROM candles WHERE symbol = ? AND timeframe = ?",
            [symbol, timeframe],
        ).fetchone()
        if result is None or result[0] is None:
            return None
        ts = result[0]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts

    # ------------------------------------------------------------------ #
    # Backup / ciclo de vida
    # ------------------------------------------------------------------ #

    def backup(self) -> Optional[Path]:
        """Snapshot diário do arquivo .duckdb (um por dia, idempotente)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        target = self.backup_dir / f"crypto_bot_{today}.duckdb"
        if target.exists():
            return None
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        # CHECKPOINT garante que o WAL esteja aplicado antes da cópia
        self.con.execute("CHECKPOINT")
        shutil.copy2(self.path, target)
        logger.info("database.backup.created", path=str(target))
        return target

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None


# Instância global (conexão lazy — só abre no primeiro uso)
db = Database()

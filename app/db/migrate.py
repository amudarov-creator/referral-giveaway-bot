"""Run Alembic migrations programmatically (for hosts without a shell)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.logging import get_logger

logger = get_logger(__name__)


def run_migrations() -> None:
    """Apply all pending migrations to the database from DATABASE_URL."""
    # Project root: /app in Docker, or repo root locally
    root = Path(__file__).resolve().parents[2]
    ini = root / "alembic.ini"
    if not ini.exists():
        # Fallback if package layout differs
        root = Path("/app")
        ini = root / "alembic.ini"
    if not ini.exists():
        raise FileNotFoundError(f"alembic.ini not found near {Path(__file__).resolve()}")

    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(root / "alembic"))
    # sqlalchemy.url is overridden in alembic/env.py from settings / env
    logger.info("running_migrations", alembic_ini=str(ini))
    command.upgrade(cfg, "head")
    logger.info("migrations_complete")

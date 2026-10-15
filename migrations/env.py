import os
from pathlib import Path

from alembic import context
from dotenv import dotenv_values
from sqlalchemy import create_engine

from backend.app.memory.store import metadata

path = Path(os.environ.get("CODEPET_DATABASE", ".codepet/memory.db"))
# Settings reads .env for the CLI, without requiring a token for migrations.

path = Path(
    os.environ.get("CODEPET_DATABASE", dotenv_values(".env").get("CODEPET_DATABASE") or str(path))
)
path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
engine = create_engine(f"sqlite:///{path}")
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()

import os
from pathlib import Path

from dotenv import load_dotenv

# Resolve configuration independently from the directory used to start uvicorn.
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_DIR = BACKEND_DIR.parent

# Support both layouts:
#   project/.env
#   backend/.env
load_dotenv(PROJECT_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env", override=False)


def resolve_path(value: str) -> str:
    """Resolve relative paths against the backend directory."""
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    return str((BACKEND_DIR / path).resolve())


def get_database_url() -> str:
    """Return a SQLAlchemy URL for local and managed PostgreSQL providers."""
    url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:indus@localhost:5432/production_optimizer",
    )

    # Render and many other providers supply a standard libpq URL. SQLAlchemy
    # needs the driver-qualified form used by this application.
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")

    return url


DATABASE_URL = get_database_url()

DATASET_PATH = resolve_path(
    os.getenv(
        "DATASET_PATH",
        "production_optimizer_dataset_v2.xlsx",
    )
)

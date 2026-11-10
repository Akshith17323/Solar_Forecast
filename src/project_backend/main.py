"""Default entry point: run from the repository root."""

from project_backend.api import create_app

app = create_app()

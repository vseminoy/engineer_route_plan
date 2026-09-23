# Run with `uvicorn src.main:app --port 8001 --no-access-log` — the request-logging
# middleware in `create_app` replaces uvicorn's own access log.
from src.app import create_app

app = create_app()

from services.api.app.core.app import create_app
from services.api.app.core.logging import setup_logging

setup_logging()

app = create_app()

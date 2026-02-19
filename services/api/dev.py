import uvicorn

from services.api.app.core.logging import LOGGING

if __name__ == "__main__":
    uvicorn.run(
        app="services.api.main:app",
        host="0.0.0.0",
        port=8900,
        reload=True,
        reload_includes=["*.py"],
        log_config=LOGGING,
        log_level="info"
    )

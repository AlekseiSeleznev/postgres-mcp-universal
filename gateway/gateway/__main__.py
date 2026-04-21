import logging
import uvicorn

from gateway.config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

if __name__ == "__main__":
    uvicorn.run(
        "gateway.server:app",
        host="0.0.0.0",
        port=settings.port,
        log_level=settings.log_level.lower(),
    )

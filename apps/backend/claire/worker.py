"""Foundation worker: database heartbeat and graceful shutdown; no ingestion yet."""

import logging
import signal
import threading

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from .config import Settings

logger = logging.getLogger("claire.worker")


def main():
    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    engine = create_engine(Settings().db_url(), pool_pre_ping=True)
    while not stop.is_set():
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            logger.info("worker heartbeat; ingestion not enabled")
        except SQLAlchemyError:
            logger.error("worker database unavailable")
        stop.wait(30)
    engine.dispose()


if __name__ == "__main__":
    main()

"""Utilities to help with logging."""
import logging


def set_loggers_level(loggers: tuple[str, ...], loglevel):
    """Set the log level for specified loggers."""
    for logger_str in loggers:
        logging.getLogger(logger_str).setLevel(loglevel)


def setup_logging(
        loglevel: str,
        logger: logging.Logger,
        aux_loggers: tuple[str, ...]
):
    """Setup logging in a most generic way."""
    logging.basicConfig(
        encoding="utf-8",
        format="%(asctime)s - %(name)s - %(levelname)s — %(message)s",
        loglevel=logging.INFO)
    logger.setLevel(getattr(logging, loglevel.upper()))
    set_loggers_level(aux_loggers, logger.getEffectiveLevel())
    return logger

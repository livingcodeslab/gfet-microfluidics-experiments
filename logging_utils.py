"""Utilities to help with logging."""
import logging

def set_loggers_level(loggers: tuple[str, ...], loglevel):
    for logger_str in loggers:
        logging.getLogger(logger_str).setLevel(loglevel)

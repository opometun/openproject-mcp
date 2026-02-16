import logging


def setup_logging(level: str = "INFO") -> None:
    """Initialize root logging with a given level (default INFO)."""
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO))


__all__ = ["setup_logging"]

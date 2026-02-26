"""
Configuración centralizada de logging para HTV Publicador.
Los logs se guardan en logs/app.log (rotando a 2 MB, max 5 ficheros).
"""

import logging
import os
from logging.handlers import RotatingFileHandler

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "app.log")

def get_logger(name: str) -> logging.Logger:
    """Devuelve un logger con salida a fichero y consola."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # ya inicializado

    logger.setLevel(logging.DEBUG)

    os.makedirs(_LOG_DIR, exist_ok=True)

    # Handler de fichero con rotación
    fh = RotatingFileHandler(
        _LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)

    # Handler de consola (solo WARNING y superior)
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

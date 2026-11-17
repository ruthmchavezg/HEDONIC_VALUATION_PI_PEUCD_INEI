"""Logging uniforme para todo el pipeline."""
from __future__ import annotations

import logging
import sys


def get_logger(nombre: str = "pi_nlp") -> logging.Logger:
    log = logging.getLogger(nombre)
    if not log.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%H:%M:%S"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
    return log

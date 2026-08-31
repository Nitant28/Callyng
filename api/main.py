"""ASGI entrypoint alias.

The real app lives in ``server:app`` (port 7860). This module exists so
``uvicorn api.main:app`` also works.
"""

from server import app

__all__ = ["app"]

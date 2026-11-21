"""Vercel-discoverable adapter, sharing the standard ASGI application."""
from backend.main import app

__all__ = ["app"]

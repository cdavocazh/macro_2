"""
WSGI entrypoint for Gunicorn.

Usage:
    gunicorn wsgi:server -b 0.0.0.0:8050 -w 2
"""
from app import server  # noqa: F401 — Gunicorn discovers this

if __name__ == "__main__":
    server.run()

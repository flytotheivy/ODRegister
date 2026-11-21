"""Reserved paths never reach the SPA fallback; only generated web assets are served."""

import re
from pathlib import Path
from urllib.parse import unquote

from starlette.routing import Match

WEB = Path(__file__).resolve().parents[1] / "web"
PRIVATE_ROOTS = {
    "backend",
    "frontend",
    "scripts",
    "tests",
    "test-data",
    "reference",
    "contracts",
    "infra",
    "docs",
    "logs",
    "web",
    "requirements.txt",
    "pyproject.toml",
    "uv.lock",
    "app.py",
    "build.py",
    "vercel.json",
    "makefile",
    "package.json",
    "package-lock.json",
}


def private_path(path):
    decoded = unquote(path).replace("\\", "/")
    parts = [p for p in decoded.split("/") if p]
    if parts and parts[0] == "assets" and not WEB.joinpath(*parts).is_file():
        return True
    return any(p.startswith(".") for p in parts) or bool(
        parts and (parts[0].lower() in PRIVATE_ROOTS or re.match(r"^\d{2}\.", parts[0]))
    )


def unknown_api(request, app):
    root = request.scope.get("root_path", "")
    path = request.scope["path"]
    if root and path.startswith(root + "/"):
        path = path[len(root) :]
    if not (path == "/api" or path.startswith("/api/")):
        return False
    # Frontends are kept outside normal app.routes by FastAPI. A partial match
    # must reach the router so unsupported methods retain their 405/Allow result.
    return not any(
        route.matches(request.scope)[0] != Match.NONE for route in app.routes
    )

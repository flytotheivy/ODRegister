"""Build only the approved UI assets. No credentials, DB access, migrations or seed."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ALLOWED = {
    ".js",
    ".css",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
}


def build():
    subprocess.run(
        [
            "npm",
            "--prefix",
            str(ROOT / "frontend"),
            "ci",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
        ],
        check=True,
    )
    subprocess.run(
        ["npm", "--prefix", str(ROOT / "frontend"), "run", "build"], check=True
    )
    source = ROOT / "frontend/dist"
    target = ROOT / "web"
    marker = ROOT / "backend/web_manifest.json"
    if target.exists() and not marker.is_file():
        raise RuntimeError("Unknown web directory; refusing overwrite")
    files = []
    for path in source.rglob("*"):
        if path.is_symlink():
            raise RuntimeError("Symlink in frontend output")
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if str(relative) != "index.html" and (
            relative.parts[0] != "assets" or path.suffix not in ALLOWED
        ):
            raise RuntimeError("Unapproved frontend output")
        files.append(relative)
    if Path("index.html") not in files:
        raise RuntimeError("Frontend index missing")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir()
    entries = []
    for relative in sorted(files):
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, dest)
        entries.append(
            {
                "path": relative.as_posix(),
                "bytes": dest.stat().st_size,
                "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
            }
        )
    marker.write_text(
        json.dumps(
            {"version": 1, "source": "frontend/dist", "files": entries}, indent=2
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "web_files": len(entries),
                "web_bytes": sum(f["bytes"] for f in entries),
                "database_used": False,
            }
        )
    )


if __name__ == "__main__":
    build()

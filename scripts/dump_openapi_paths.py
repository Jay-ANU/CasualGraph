"""Print every registered HTTP route as ``METHOD path`` lines, sorted.

Used to prove that a refactor did not add or drop endpoints::

    python scripts/dump_openapi_paths.py > /tmp/before.txt
    # ... refactor ...
    python scripts/dump_openapi_paths.py > /tmp/after.txt
    diff /tmp/before.txt /tmp/after.txt
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("APP_ENV", "development")


def _iter_routes(app):
    """Yield route-like objects with ``path``/``methods``, expanding ``include_router()``.

    Recent FastAPI versions keep included routers as lazy entries in ``app.routes``;
    ``iter_route_contexts`` walks their effective routes. Older versions list routes flat.
    """
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:
        return list(app.routes)
    return list(iter_route_contexts(app.routes))


def main() -> int:
    from app import app  # noqa: WPS433  (import after sys.path tweak)

    lines = set()
    for route in _iter_routes(app):
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path:
            continue
        if not methods:  # mounts / static files
            lines.add(f"MOUNT {path}")
            continue
        for method in sorted(methods):
            if method == "HEAD":
                continue
            lines.add(f"{method} {path}")
    for line in sorted(lines):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

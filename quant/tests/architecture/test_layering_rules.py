from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
HTTP_DIR = SRC / "interfaces" / "http"
APP_DIR = SRC / "application"


def _imports(file_path: Path) -> list[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_http_routes_do_not_import_application_directly():
    violations: list[str] = []
    for py in HTTP_DIR.glob("*.py"):
        if py.name in {"__init__.py", "dependencies.py"}:
            continue
        imports = _imports(py)
        if any(name == "application" or name.startswith("application.") for name in imports):
            violations.append(str(py.relative_to(ROOT)))

    assert not violations, f"HTTP layer must use providers, direct application imports found: {violations}"


def test_application_layer_does_not_depend_on_fastapi():
    violations: list[str] = []
    for py in APP_DIR.rglob("*.py"):
        imports = _imports(py)
        if any(name == "fastapi" or name.startswith("fastapi.") for name in imports):
            violations.append(str(py.relative_to(ROOT)))

    assert not violations, f"Application layer must not import FastAPI: {violations}"

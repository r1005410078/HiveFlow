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


def test_application_decision_can_import_domain():
    """application.decision 可以依赖 domain 层"""
    decision_dir = APP_DIR / "decision"
    for py in decision_dir.rglob("*.py"):
        imports = _imports(py)
        has_domain = any(name == "domain" or name.startswith("domain.") for name in imports)
        # This test merely asserts the module can be parsed without error.
        # The real constraint is the negative tests below.
    # If we reach here without error, the module parses fine.
    assert decision_dir.exists(), "application/decision directory must exist"


def test_application_decision_does_not_import_interfaces():
    """application.decision 禁止依赖 interfaces 层"""
    decision_dir = APP_DIR / "decision"
    violations: list[str] = []
    for py in decision_dir.rglob("*.py"):
        imports = _imports(py)
        if any(name == "interfaces" or name.startswith("interfaces.") for name in imports):
            violations.append(str(py.relative_to(ROOT)))

    assert not violations, f"application.decision must not import interfaces: {violations}"


def test_domain_models_do_not_import_application_or_interfaces():
    """domain.models 禁止依赖 application 或 interfaces 层"""
    domain_models_dir = SRC / "domain" / "models"
    violations: list[str] = []
    for py in domain_models_dir.rglob("*.py"):
        imports = _imports(py)
        for name in imports:
            if name == "application" or name.startswith("application.") or \
               name == "interfaces" or name.startswith("interfaces."):
                violations.append(f"{py.relative_to(ROOT)}: imports {name}")

    assert not violations, f"domain.models must not import application or interfaces: {violations}"

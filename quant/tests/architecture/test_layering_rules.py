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
    """application.decision 内至少有一个文件引用 domain 层"""
    decision_dir = APP_DIR / "decision"
    assert decision_dir.exists(), "application/decision directory must exist"
    py_files = list(decision_dir.glob("*.py"))
    assert any(
        "from domain" in f.read_text() or "import domain" in f.read_text()
        for f in py_files
    ), "At least one file in application/decision must import from domain"


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


def test_application_signal_does_not_import_interfaces():
    """application.signal 禁止依赖 interfaces 层"""
    signal_dir = APP_DIR / "signal"
    if not signal_dir.exists():
        return
    violations: list[str] = []
    for py in signal_dir.rglob("*.py"):
        imports = _imports(py)
        if any(name == "interfaces" or name.startswith("interfaces.") for name in imports):
            violations.append(str(py.relative_to(ROOT)))
    assert not violations, f"application.signal must not import interfaces: {violations}"


def test_domain_signal_does_not_import_application():
    """domain.models.signal 禁止依赖 application"""
    signal_file = SRC / "domain" / "models" / "signal.py"
    if not signal_file.exists():
        return
    imports = _imports(signal_file)
    violations = [name for name in imports if name == "application" or name.startswith("application.")]
    assert not violations, f"domain.models.signal must not import application: {violations}"


def test_application_portfolio_does_not_import_interfaces():
    """application.portfolio 禁止依赖 interfaces 层"""
    portfolio_dir = APP_DIR / "portfolio"
    if not portfolio_dir.exists():
        return
    violations: list[str] = []
    for py in portfolio_dir.rglob("*.py"):
        imports = _imports(py)
        if any(name == "interfaces" or name.startswith("interfaces.") for name in imports):
            violations.append(str(py.relative_to(ROOT)))
    assert not violations, f"application.portfolio must not import interfaces: {violations}"


def test_application_technical_does_not_import_interfaces():
    """application.technical 禁止依赖 interfaces 层"""
    technical_dir = APP_DIR / "technical"
    if not technical_dir.exists():
        return
    violations: list[str] = []
    for py in technical_dir.rglob("*.py"):
        imports = _imports(py)
        if any(name == "interfaces" or name.startswith("interfaces.") for name in imports):
            violations.append(str(py.relative_to(ROOT)))
    assert not violations, f"application.technical must not import interfaces: {violations}"


def test_domain_portfolio_does_not_import_application():
    """domain.models.portfolio 禁止依赖 application"""
    portfolio_file = SRC / "domain" / "models" / "portfolio.py"
    if not portfolio_file.exists():
        return
    imports = _imports(portfolio_file)
    violations = [name for name in imports if name == "application" or name.startswith("application.")]
    assert not violations, f"domain.models.portfolio must not import application: {violations}"


def test_application_can_import_domain_universe():
    """application/* 层允许导入 domain.universe（universe loader 集中管理标的池）"""
    universe_loader = SRC / "domain" / "universe" / "universe_loader.py"
    assert universe_loader.exists(), "domain/universe/universe_loader.py must exist"
    # Verify that application services DO import from domain.universe (positive assertion)
    app_files_importing_universe = []
    for py in APP_DIR.rglob("*.py"):
        imports = _imports(py)
        if any("domain.universe" in name for name in imports):
            app_files_importing_universe.append(str(py.relative_to(ROOT)))
    assert len(app_files_importing_universe) >= 3, (
        f"At least 3 application files should import from domain.universe "
        f"(optimizer, risk_gate, signal_engineering services). Found: {app_files_importing_universe}"
    )

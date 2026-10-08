"""Garde-fous des règles de dépendance entre couches (voir docs/architecture.md).

Ces tests échouent dès qu'un import viole l'architecture, sur TOUS les domaines présents et futurs.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"

FRAMEWORKS = ("fastapi", "starlette", "sqlalchemy", "pydantic", "pydantic_settings", "alembic")


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)

    return modules


def python_files(folder: str) -> list[Path]:
    return sorted((SRC / folder).rglob("*.py"))


def starts_with_any(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(module == prefix or module.startswith(prefix + ".") for prefix in prefixes)


@pytest.mark.parametrize("path", python_files("domain"), ids=lambda p: str(p.relative_to(SRC)))
def test_domain_is_pure(path: Path) -> None:
    forbidden = (*FRAMEWORKS, "src.features", "src.infrastructure", "src.shared")
    violations = [m for m in imported_modules(path) if starts_with_any(m, forbidden)]

    assert not violations, f"domain/ doit rester pur, imports interdits : {violations}"


@pytest.mark.parametrize("path", python_files("features"), ids=lambda p: str(p.relative_to(SRC)))
def test_features_reach_infrastructure_only_from_router(path: Path) -> None:
    if path.name == "router.py":
        return

    forbidden = ("sqlalchemy", "src.infrastructure")
    violations = [m for m in imported_modules(path) if starts_with_any(m, forbidden)]

    assert not violations, f"seul router.py peut importer l'infrastructure : {violations}"


@pytest.mark.parametrize("path", python_files("shared"), ids=lambda p: str(p.relative_to(SRC)))
def test_shared_does_not_depend_on_features_or_infrastructure(path: Path) -> None:
    forbidden = ("src.features", "src.infrastructure", "sqlalchemy")
    violations = [m for m in imported_modules(path) if starts_with_any(m, forbidden)]

    assert not violations, f"shared/ ne doit dépendre ni des features ni de l'infra : {violations}"

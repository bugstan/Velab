from __future__ import annotations

from pathlib import Path

import pytest

# Package root = backend/log_pipeline/ — used to resolve config YAMLs in tests
# that build Settings with relative paths.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _cwd_at_package_root(monkeypatch):
    """Several tests build ``Settings(classifier_yaml=Path("config/...yaml"))``
    with relative paths — anchor cwd to the package root so those resolve
    consistently regardless of where pytest was invoked from."""
    monkeypatch.chdir(_PACKAGE_ROOT)
    yield


@pytest.fixture
def classifier_yaml() -> Path:
    return _PACKAGE_ROOT / "config" / "controllers.yaml"


@pytest.fixture
def store_root(tmp_path: Path) -> Path:
    d = tmp_path / "store"
    d.mkdir()
    return d


@pytest.fixture
def work_root(tmp_path: Path) -> Path:
    d = tmp_path / "work"
    d.mkdir()
    return d


@pytest.fixture
def catalog_db(tmp_path: Path) -> Path:
    return tmp_path / "catalog.db"

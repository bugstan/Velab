from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


_PACKAGE_ROOT = Path(__file__).resolve().parent
_BACKEND_ROOT = _PACKAGE_ROOT.parent
_DEFAULT_DATA_ROOT = _BACKEND_ROOT / "data"
_CONFIG_ROOT = _PACKAGE_ROOT / "config"


@dataclass(frozen=True)
class Settings:
    store_root: Path
    """Where extracted bundle files live on disk."""

    upload_root: Path
    """Where uploaded archives are temporarily kept before extraction."""

    work_root: Path
    """Scratch space for extractor temp output (cleaned after ingest)."""

    index_root: Path
    """Where bucket-index ``.idx`` files live on disk (one subdir per bundle)."""

    catalog_db: Path
    """SQLite catalog database path."""

    classifier_yaml: Path
    """Path to controllers.yaml."""

    event_rules_yaml: Path
    """Path to event_rules.yaml."""

    anchor_rules_yaml: Path
    """Path to anchor_rules.yaml."""

    slim_rules_yaml: Path
    """Path to slim_rules.yaml (query-time line filter)."""

    @classmethod
    def from_env(cls) -> "Settings":
        data_root = Path(os.environ.get("LOG_PIPELINE_DATA_ROOT", _DEFAULT_DATA_ROOT))
        config_root = _CONFIG_ROOT
        return cls(
            store_root=Path(os.environ.get("LOG_PIPELINE_STORE_ROOT", data_root / "bundles")),
            upload_root=Path(os.environ.get("LOG_PIPELINE_UPLOAD_ROOT", data_root / "uploads")),
            work_root=Path(os.environ.get("LOG_PIPELINE_WORK_ROOT", data_root / "work")),
            index_root=Path(os.environ.get("LOG_PIPELINE_INDEX_ROOT", data_root / "indexes")),
            catalog_db=Path(os.environ.get("LOG_PIPELINE_CATALOG_DB", data_root / "catalog.db")),
            classifier_yaml=Path(
                os.environ.get("LOG_PIPELINE_CLASSIFIER_YAML", config_root / "controllers.yaml")
            ),
            event_rules_yaml=Path(
                os.environ.get("LOG_PIPELINE_EVENT_RULES", config_root / "event_rules.yaml")
            ),
            anchor_rules_yaml=Path(
                os.environ.get("LOG_PIPELINE_ANCHOR_RULES", config_root / "anchor_rules.yaml")
            ),
            slim_rules_yaml=Path(
                os.environ.get("LOG_PIPELINE_SLIM_RULES", config_root / "slim_rules.yaml")
            ),
        )

    def ensure_dirs(self) -> None:
        for d in (self.store_root, self.upload_root, self.work_root, self.index_root):
            d.mkdir(parents=True, exist_ok=True)
        self.catalog_db.parent.mkdir(parents=True, exist_ok=True)

"""Central configuration; paths are independent of the current shell directory."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import dotenv_values
import os


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FROZEN_REFERENCE_DATE = date(2026, 10, 20)


@dataclass(frozen=True)
class Settings:
    project_root: Path
    dataset_dir: Path
    artifacts_dir: Path
    reference_date: date

    def validate_dataset_layout(self) -> None:
        """Check required folders without importing tools or reading customer data."""
        missing = [
            str(self.dataset_dir / name)
            for name in ("kb", "data", "practice", "tools")
            if not (self.dataset_dir / name).is_dir()
        ]
        if missing:
            raise ValueError("Missing dataset folders: " + ", ".join(missing))


def load_settings(project_root: Path | None = None) -> Settings:
    """Read .env without changing process state; environment variables take priority."""
    root = (project_root or PROJECT_ROOT).resolve()
    values = {**dotenv_values(root / ".env"), **os.environ}

    def resolve_path(key: str, default: str) -> Path:
        configured = Path(values.get(key) or default).expanduser()
        return (root / configured).resolve()

    reference_date = date.fromisoformat(
        values.get("DATASET_REFERENCE_DATE") or FROZEN_REFERENCE_DATE.isoformat()
    )
    if reference_date != FROZEN_REFERENCE_DATE:
        raise ValueError("This dataset requires DATASET_REFERENCE_DATE=2026-10-20.")

    return Settings(
        project_root=root,
        dataset_dir=resolve_path("DATASET_DIR", "dataset"),
        artifacts_dir=resolve_path("ARTIFACTS_DIR", "artifacts"),
        reference_date=reference_date,
    )

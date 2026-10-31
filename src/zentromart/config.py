"""Central configuration; paths are independent of the current shell directory."""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from dotenv import dotenv_values
import os
import re


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FROZEN_REFERENCE_DATE = date(2026, 10, 20)


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    api_key: str = field(repr=False)
    timeout_seconds: int = 20
    max_output_tokens: int = 1024
    retries: int = 1

    def __post_init__(self) -> None:
        if self.provider != "gemini":
            raise ValueError("Set LLM_PROVIDER=gemini; other providers are not implemented")
        if not re.fullmatch(r"gemini-[a-z0-9._-]{1,100}", self.model):
            raise ValueError("Set LLM_MODEL to an explicit Gemini model ID")
        if not isinstance(self.api_key, str) or any(char.isspace() for char in self.api_key):
            raise ValueError("LLM_API_KEY must be a single value without whitespace")
        for value, minimum, maximum, name in (
            (self.timeout_seconds, 1, 60, "LLM_TIMEOUT_SECONDS"),
            (self.max_output_tokens, 128, 4096, "LLM_MAX_OUTPUT_TOKENS"),
            (self.retries, 0, 2, "LLM_RETRIES"),
        ):
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")

    def require_key(self) -> None:
        if not self.api_key or self.api_key.lower().startswith(("your_", "your-", "paste_", "replace_")):
            raise ValueError("Set LLM_API_KEY in the local .env file before a live request")


def load_llm_settings(project_root: Path | None = None) -> LLMSettings:
    """Load model configuration only when requested, without mutating the environment."""
    root = (project_root or PROJECT_ROOT).resolve()
    values = {**dotenv_values(root / ".env"), **os.environ}

    def integer(key: str, default: int) -> int:
        try:
            return int(values.get(key) or default)
        except (ValueError, TypeError):
            raise ValueError(f"{key} must be an integer") from None

    return LLMSettings(
        provider=(values.get("LLM_PROVIDER") or "").strip().lower(),
        model=(values.get("LLM_MODEL") or "").strip(),
        api_key=(values.get("LLM_API_KEY") or "").strip(),
        timeout_seconds=integer("LLM_TIMEOUT_SECONDS", 20),
        max_output_tokens=integer("LLM_MAX_OUTPUT_TOKENS", 1024),
        retries=integer("LLM_RETRIES", 1),
    )


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


@dataclass(frozen=True)
class RetrievalSettings:
    method: str = "hybrid"
    offline: bool = False
    embedding_model: str = "bge-m3"
    reranker: str = "none"

    def __post_init__(self):
        if self.method not in {"bm25", "semantic", "hybrid"} or type(self.offline) is not bool:
            raise ValueError("Invalid retrieval configuration")
        if self.embedding_model not in {"e5-small", "bge-m3"} or self.reranker not in {"none", "mmarco-minilm"}:
            raise ValueError("Invalid embedding or reranker configuration")


def load_retrieval_settings(project_root: Path | None = None):
    root = (project_root or PROJECT_ROOT).resolve()
    values = {**dotenv_values(root / ".env"), **os.environ}
    flag = str(values.get("RETRIEVAL_OFFLINE") or "false").strip().lower()
    if flag not in {"true", "false"}:
        raise ValueError("RETRIEVAL_OFFLINE must be true or false")
    return RetrievalSettings(str(values.get("RETRIEVER") or "hybrid").strip().lower(), flag == "true",
        str(values.get("EMBEDDING_MODEL") or "bge-m3").strip().lower(),
        str(values.get("RERANKER") or "none").strip().lower())


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

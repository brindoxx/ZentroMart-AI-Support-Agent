"""Run a credentials-free setup check with python -m zentromart."""

from .config import load_settings


def main() -> None:
    try:
        settings = load_settings()
        settings.validate_dataset_layout()
    except ValueError as exc:
        raise SystemExit(f"Setup check failed: {exc}") from exc
    print("ZentroMart project setup is ready.")
    print(f"Dataset: {settings.dataset_dir}")
    print(f"Reference date: {settings.reference_date}")
    print("Phase 1 complete. Retrieval, chat, and voice are planned for later phases.")


if __name__ == "__main__":
    main()

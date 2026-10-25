"""Offline setup, inspection, and supplied dataset validation commands."""

import argparse
import json
import subprocess
import sys

from .config import load_settings
from .dataset import format_inspection, inspect_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command")
    inspection = commands.add_parser("inspect", help="Show dataset schema and counts")
    inspection.add_argument("--json", action="store_true", help="Print the inspection as JSON")
    commands.add_parser("validate", help="Run the supplied offline dataset validator")
    args = parser.parse_args()
    try:
        settings = load_settings()
        settings.validate_dataset_layout()
        if args.command == "inspect":
            report = inspect_dataset(settings.dataset_dir)
            print(json.dumps(report, indent=2) if args.json else format_inspection(report))
            raise SystemExit(1 if report["issues"] else 0)
        if args.command == "validate":
            validator = settings.dataset_dir / "validate_dataset.py"
            if not validator.is_file():
                raise ValueError("Dataset validator is missing")
            # Isolate the supplied validator's imports and global state. It tests
            # rejected ticket creation only, so it does not create ticket records.
            result = subprocess.run(
                [sys.executable, "-X", "utf8", str(validator)],
                cwd=settings.dataset_dir, check=False,
            )
            raise SystemExit(result.returncode)
    except (ValueError, OSError) as exc:
        raise SystemExit(f"Dataset command failed: {exc}") from exc
    print("ZentroMart project setup is ready.")
    print(f"Dataset: {settings.dataset_dir}")
    print(f"Reference date: {settings.reference_date}")
    print("Use 'python -m zentromart inspect' or 'python -m zentromart validate'.")


if __name__ == "__main__":
    main()

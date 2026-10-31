"""Offline dataset inspection. Reports contain schema and counts, never row values.

These helpers are for development and validation. The customer-facing
agent must obtain private order data through the verified lookup tool instead.
"""

from collections import Counter
import csv
from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class TableSpec:
    path: str
    primary_key: tuple[str, ...]
    expected_rows: int


TABLES = {
    "customers": TableSpec("data/customers.csv", ("customer_id",), 300),
    "orders": TableSpec("data/orders.csv", ("order_id",), 1000),
    "order_items": TableSpec("data/order_items.csv", ("order_id", "line_no"), 1783),
    "products": TableSpec("data/products.csv", ("sku",), 70),
    "pincodes": TableSpec("data/pincodes.csv", ("pincode",), 36),
    "holidays": TableSpec("data/holidays.csv", ("date",), 4),
    "support_logs": TableSpec("data/support_logs.csv", ("log_id",), 244),
    "questions": TableSpec("practice/questions.csv", ("id",), 52),
    "conversations": TableSpec(
        "practice/conversations.csv", ("conversation_id", "turn"), 96
    ),
}

# child table, child field, parent table, parent key
RELATIONSHIPS = (
    ("orders", "customer_id", "customers", "customer_id"),
    ("orders", "delivery_pincode", "pincodes", "pincode"),
    ("customers", "pincode", "pincodes", "pincode"),
    ("order_items", "order_id", "orders", "order_id"),
    ("order_items", "sku", "products", "sku"),
    ("support_logs", "order_id", "orders", "order_id"),
    ("support_logs", "customer_id", "customers", "customer_id"),
    ("conversations", "order_id", "orders", "order_id"),
    ("conversations", "customer_id", "customers", "customer_id"),
)


def read_table(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Keep every cell as text, including leading zeros and empty strings.

    newline='' lets the CSV parser handle quoted multiline transcripts. Reject
    malformed row widths rather than silently dropping or inventing cell values.
    """
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        columns = reader.fieldnames
        if not columns or any(not name.strip() for name in columns):
            raise ValueError(f"{path.name}: missing or blank column names")
        if len(columns) != len(set(columns)):
            raise ValueError(f"{path.name}: duplicate column names")
        rows = []
        try:
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(
                        f"{path.name}: wrong number of cells near line {reader.line_num}"
                    )
                rows.append(row)
        except csv.Error:
            raise ValueError(f"{path.name}: malformed CSV near line {reader.line_num}") from None
    return columns, rows


def require_columns(columns: list[str], required: tuple[str, ...], label: str) -> None:
    missing = sorted(set(required) - set(columns))
    if missing:
        raise ValueError(f"{label}: missing required columns: {', '.join(missing)}")


def summarize_table(
    columns: list[str], rows: list[dict[str, str]], spec: TableSpec
) -> dict:
    require_columns(columns, spec.primary_key, spec.path)
    keys = [tuple(row[column] for column in spec.primary_key) for row in rows]
    return {
        "path": spec.path,
        "rows": len(rows),
        "expected_rows": spec.expected_rows,
        "columns": columns,
        "primary_key": list(spec.primary_key),
        "duplicate_key_rows": len(keys) - len(set(keys)),
        "blank_key_rows": sum(any(not part.strip() for part in key) for key in keys),
        "empty_cells": {
            column: sum(row[column] == "" for row in rows) for column in columns
        },
    }


def check_relationship(
    child: list[dict[str, str]], child_field: str,
    parent: list[dict[str, str]], parent_field: str,
) -> dict[str, int]:
    parent_keys = {row[parent_field] for row in parent if row[parent_field]}
    return {
        "checked_rows": sum(bool(row[child_field].strip()) for row in child),
        "blank_reference_rows": sum(not row[child_field].strip() for row in child),
        "broken_reference_rows": sum(
            bool(row[child_field].strip()) and row[child_field] not in parent_keys
            for row in child
        ),
    }


def inspect_dataset(root: Path) -> dict:
    """Inspect the supplied tables and public document inventory without mutations."""
    tables, loaded, headers, issues = {}, {}, {}, []
    for name, spec in TABLES.items():
        columns, rows = read_table(root / spec.path)
        headers[name], loaded[name] = columns, rows
        tables[name] = summary = summarize_table(columns, rows, spec)
        if summary["rows"] != spec.expected_rows:
            issues.append(f"{name}: unexpected row count")
        if summary["duplicate_key_rows"] or summary["blank_key_rows"]:
            issues.append(f"{name}: invalid primary keys")

    relationships = []
    for child, field, parent, key in RELATIONSHIPS:
        require_columns(headers[child], (field,), TABLES[child].path)
        require_columns(headers[parent], (key,), TABLES[parent].path)
        counts = check_relationship(loaded[child], field, loaded[parent], key)
        relationships.append({
            "child": f"{child}.{field}", "parent": f"{parent}.{key}", **counts
        })
        if counts["broken_reference_rows"]:
            issues.append(f"{child}.{field}: broken references")

    documents, section_ids = [], []
    for path in sorted((root / "kb").glob("*.md")):
        text = path.read_text(encoding="utf-8-sig")
        # Inventory only; ingestion owns full metadata parsing and retrieval chunks.
        header = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
        if not header:
            raise ValueError(f"{path.name}: missing document metadata header")
        metadata = dict(re.findall(r"^(\w+):\s*(.*?)\s*$", header[1], re.M))
        required = ("doc_id", "doc_type", "status", "effective_from")
        if any(not metadata.get(field) for field in required):
            raise ValueError(f"{path.name}: incomplete document metadata")
        ids = re.findall(r"^##\s*\[([^\]]+)\]", text, re.M)
        section_ids.extend(ids)
        documents.append({
            "path": f"kb/{path.name}",
            **{field: metadata[field] for field in required},
            "sections": len(ids),
        })
    if len(documents) != 21:
        issues.append("knowledge base: expected 21 documents")
    if len(section_ids) != len(set(section_ids)):
        issues.append("knowledge base: duplicate section IDs")
    require_columns(headers["questions"], ("language",), TABLES["questions"].path)
    require_columns(headers["conversations"], ("conversation_id",), TABLES["conversations"].path)
    # Only known language codes appear as output labels; never echo arbitrary cell text.
    language_counts = Counter(row["language"] for row in loaded["questions"])
    languages = {code: language_counts[code] for code in ("en", "hi", "hi-en")}
    languages["other"] = sum(language_counts.values()) - sum(languages.values())
    return {
        "tables": tables,
        "relationships": relationships,
        "knowledge_base": {
            "documents": documents,
            "total_sections": len(section_ids),
            "unique_sections": len(set(section_ids)),
        },
        "practice": {
            "question_languages": languages,
            "conversations": len({r["conversation_id"] for r in loaded["conversations"]}),
            "turns": len(loaded["conversations"]),
        },
        "issues": issues,
    }


def format_inspection(report: dict) -> str:
    lines = ["ZentroMart dataset inspection (schema and counts only)", ""]
    for name, table in report["tables"].items():
        lines.append(
            f"{name}: {table['rows']} rows, {len(table['columns'])} columns; "
            f"primary key: {', '.join(table['primary_key'])}"
        )
        blanks = [f"{key}={count}" for key, count in table["empty_cells"].items() if count]
        lines.append("  Empty cells: " + (", ".join(blanks) or "none"))
    lines.append("\nRelationships:")
    for relation in report["relationships"]:
        lines.append(
            f"  {relation['child']} -> {relation['parent']}: "
            f"{relation['broken_reference_rows']} broken, "
            f"{relation['blank_reference_rows']} blank"
        )
    kb = report["knowledge_base"]
    lines.append(f"\nKnowledge base: {len(kb['documents'])} documents, {kb['total_sections']} sections")
    for document in kb["documents"]:
        lines.append(f"  {document['path']}: {document['status']}, {document['sections']} sections")
    practice = report["practice"]
    lines.append(f"\nPractice: {practice['conversations']} conversations, {practice['turns']} turns")
    lines.append(f"Question languages: {practice['question_languages']}")
    lines.append("\nInspection: " + ("FAIL" if report["issues"] else "PASS"))
    lines.extend(report["issues"])
    lines.append("Run 'python -m zentromart validate' for the supplied deeper validation.")
    return "\n".join(lines)

"""Parse the supplied Markdown knowledge base into provenance-preserving sections.

Only kb/*.md is read. This module does not load customers, orders, support logs,
or practice labels. Metadata parsing supports the pack's flat string fields,
not arbitrary YAML. Section splitting supports ATX headings and fenced blocks.
"""

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4


@dataclass(frozen=True)
class DocumentMetadata:
    doc_id: str
    title: str
    doc_type: str
    audience: str
    language: str
    version: str
    effective_from: str
    status: str
    supersedes: str | None = None
    superseded_by: str | None = None


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    section_id: str
    section_title: str
    source: str
    line_start: int
    line_end: int
    source_sha256: str
    metadata: DocumentMetadata
    document_context: str
    content: str

    @property
    def search_text(self) -> str:
        """Include titles and pre-section guidance with the complete section."""
        return "\n\n".join(part for part in (
            self.metadata.title, self.document_context, self.content
        ) if part)

    def to_dict(self) -> dict:
        return {**asdict(self), "search_text": self.search_text}


REQUIRED_FIELDS = {
    "doc_id", "title", "doc_type", "audience", "language", "version", "effective_from", "status"
}
OPTIONAL_FIELDS = {"supersedes", "superseded_by"}
DOC_TYPES = {"meta", "policy", "agent_guide", "help", "faq", "marketing"}
SECTION = re.compile(r"^ {0,3}##[ \t]+\[([A-Za-z0-9][A-Za-z0-9.-]*)\][ \t]+(.+?)\s*$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def _metadata(lines: list[str], source: str) -> tuple[DocumentMetadata, int]:
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{source}: missing opening metadata delimiter")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise ValueError(f"{source}: missing closing metadata delimiter")
    fields = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        match = re.fullmatch(r"([a-z_]+):[ \t]*(.*?)\s*", line.rstrip("\r\n"))
        if not match or not match[2]:
            raise ValueError(f"{source}: expected a flat, nonempty metadata field")
        key, value = match.groups()
        if key not in REQUIRED_FIELDS | OPTIONAL_FIELDS or key in fields:
            raise ValueError(f"{source}: unknown or duplicate metadata key")
        if value[0] == '"':
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise ValueError(f"{source}: invalid quoted metadata value") from None
        elif value[0] == "'":
            if len(value) < 2 or not value.endswith("'"):
                raise ValueError(f"{source}: invalid quoted metadata value")
            value = value[1:-1].replace("''", "'")
        elif value[0] in "[{|>&*!":
            raise ValueError(f"{source}: nested or special YAML values are unsupported")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{source}: metadata values must be nonempty strings")
        fields[key] = value
    missing = REQUIRED_FIELDS - fields.keys()
    if missing:
        raise ValueError(f"{source}: missing metadata fields: {', '.join(sorted(missing))}")
    if fields["doc_type"] not in DOC_TYPES or fields["status"] not in {"current", "superseded"}:
        raise ValueError(f"{source}: invalid document type or status")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", fields["doc_id"]):
        raise ValueError(f"{source}: invalid document ID")
    if not re.fullmatch(r"\d+(?:\.\d+)*", fields["version"]):
        raise ValueError(f"{source}: invalid version")
    try:
        valid_date = date.fromisoformat(fields["effective_from"]).isoformat()
    except ValueError:
        raise ValueError(f"{source}: invalid effective_from date") from None
    if valid_date != fields["effective_from"]:
        raise ValueError(f"{source}: effective_from must use YYYY-MM-DD")
    return DocumentMetadata(**fields), end


def parse_document(text: str, source: str) -> list[KnowledgeChunk]:
    """Preserve whole sections and their original one-based source line ranges."""
    source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    lines = text.removeprefix("\ufeff").splitlines(keepends=True)
    metadata, header_end = _metadata(lines, source)
    sections = []
    fence = None
    for index in range(header_end + 1, len(lines)):
        line = lines[index].rstrip("\r\n")
        marker = FENCE.match(line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            continue
        if marker:
            fence = marker[1]
            continue
        if re.match(r"^ {0,3}##(?:[ \t]|$)", line):
            heading = SECTION.fullmatch(line)
            if not heading:
                raise ValueError(f"{source}:{index + 1}: section heading needs an ID and title")
            sections.append((index, heading[1], heading[2]))
    if fence:
        raise ValueError(f"{source}: unclosed fenced block")
    if not sections:
        raise ValueError(f"{source}: no identified sections")
    identifiers = [section[1] for section in sections]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{source}: duplicate section IDs")
    context = "".join(lines[header_end + 1:sections[0][0]]).strip()
    chunks = []
    for position, (start, section_id, title) in enumerate(sections):
        end = sections[position + 1][0] if position + 1 < len(sections) else len(lines)
        if not "".join(lines[start + 1:end]).strip():
            raise ValueError(f"{source}:{start + 1}: empty section")
        chunks.append(KnowledgeChunk(
            chunk_id=section_id, section_id=section_id, section_title=title,
            source=source, line_start=start + 1, line_end=end,
            source_sha256=source_hash, metadata=metadata, document_context=context,
            content="".join(lines[start:end]).strip(),
        ))
    return chunks


def build_corpus(dataset_dir: Path) -> list[KnowledgeChunk]:
    """Deterministic order, globally unique IDs, and valid version links."""
    files = sorted((dataset_dir / "kb").glob("*.md"))
    if not files:
        raise ValueError("No knowledge base Markdown documents found")
    chunks, documents, identifiers = [], {}, set()
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to((dataset_dir / "kb").resolve()):
            raise ValueError("Knowledge source must remain inside the kb directory")
        parsed = parse_document(path.read_bytes().decode("utf-8"), f"kb/{path.name}")
        metadata = parsed[0].metadata
        if metadata.doc_id in documents:
            raise ValueError("Duplicate knowledge document ID")
        documents[metadata.doc_id] = metadata
        for chunk in parsed:
            if chunk.chunk_id in identifiers:
                raise ValueError("Duplicate knowledge section ID across documents")
            identifiers.add(chunk.chunk_id)
        chunks.extend(parsed)
    for metadata in documents.values():
        for link in (metadata.supersedes, metadata.superseded_by):
            if link and (link not in documents or link == metadata.doc_id):
                raise ValueError("Missing or self-referential document version link")
    return chunks


def summarize_corpus(chunks: list[KnowledgeChunk]) -> dict:
    documents = {chunk.metadata.doc_id: chunk.metadata for chunk in chunks}
    sizes = [len(chunk.search_text) for chunk in chunks]
    return {
        "documents": len(documents), "chunks": len(chunks),
        "documents_by_status": dict(sorted(Counter(doc.status for doc in documents.values()).items())),
        "chunks_by_status": dict(sorted(Counter(chunk.metadata.status for chunk in chunks).items())),
        "chunks_by_language": dict(sorted(Counter(chunk.metadata.language for chunk in chunks).items())),
        "search_text_characters": {
            "min": min(sizes, default=0), "max": max(sizes, default=0),
            "mean": round(sum(sizes) / len(sizes), 1) if sizes else 0,
        },
    }


def save_corpus(chunks: list[KnowledgeChunk], artifacts_dir: Path, reference_date: date) -> Path:
    """Write portable JSONL and a manifest in a new run folder; do not overwrite."""
    if not chunks:
        raise ValueError("Cannot save an empty knowledge corpus")
    payload = "".join(json.dumps(chunk.to_dict(), ensure_ascii=False, sort_keys=True) + "\n" for chunk in chunks)
    corpus_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    directory = artifacts_dir / "knowledge" / f"{corpus_hash[:12]}-{uuid4().hex[:8]}"
    directory.mkdir(parents=True, exist_ok=False)
    with (directory / "chunks.jsonl").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    manifest = {
        "schema_version": 1, "chunking_strategy": "one_identified_section_with_document_context",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reference_date": reference_date.isoformat(), "corpus_sha256": corpus_hash,
        "sources": dict(sorted({chunk.source: chunk.source_sha256 for chunk in chunks}.items())),
        **summarize_corpus(chunks),
    }
    with (directory / "manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return directory

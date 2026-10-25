# Phase 4: turn policy files into searchable sections

## What this phase accomplishes

The source material is Markdown written for people. Retrieval needs a list of
separate passages with enough context to interpret each passage correctly.
We now convert every identified knowledge-base section into a `KnowledgeChunk`.
The actual keyword search arrives in Phase 5; embeddings arrive in Phase 6.

The distinction from Phase 2 is concrete: Phase 2 counted and checked the files.
Phase 4 produces the content records that the future retriever will search.

## Try it yourself

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m zentromart ingest
.\.venv\Scripts\python.exe -m zentromart ingest --section RET-2
.\.venv\Scripts\python.exe -m zentromart ingest --section RETv3-2
```

The first command writes a new folder under `artifacts/knowledge/` containing:

- `chunks.jsonl`: one complete JSON record per section.
- `manifest.json`: counts, the chunking strategy, source hashes, corpus hash,
  build time, and the fixed reference date.

The section-preview command prints one record without writing a new artifact.
An unknown ID exits with an error. Preview JSON uses escaped non-ASCII characters
for Windows console compatibility; saved files contain native UTF-8 text.
Artifacts stay out of Git and can be regenerated from the committed source files.

## Why one chunk per section?

Consider the returns document. `[RET-2]` contains the return-window table, while
`[RET-6]` describes reverse-pickup fees. A request about fees should retrieve the
fee section rather than receive the entire returns policy as undifferentiated
context.

A fixed split every 500 characters might cut a table in half or separate an
exception from the sentence it qualifies. The supplied section headings already
define useful boundaries, and evaluation expects those same section IDs.

Measured across the supplied pack, search entries range from 105 to 822
characters, averaging 300.1 characters. Those sizes include document context.
These are character counts, not model token counts. The passages are short
enough to retain whole sections without sliding windows or overlap.

We preserve Markdown tables, bullets, bold text, cross-references, Hindi text,
and rupee symbols. Subheadings remain in their parent section. A heading inside
a fenced code block is content, not a new chunk.

## What goes into a chunk

| Field | Purpose |
| --- | --- |
| `chunk_id`, `section_id` | Stable evidence identifier, such as `RET-2` |
| `section_title` | Human-readable topic of the section |
| `source` | Dataset-relative document path |
| `line_start`, `line_end` | Inclusive, one-based source line range |
| `source_sha256` | Fingerprint of the source UTF-8 bytes |
| `metadata` | Document ID, title, type, audience, language, version, effective date, status, and version links |
| `document_context` | Text between the metadata header and first section |
| `content` | Original identified section heading and its complete body |
| `search_text` | Document title + document context + section content |

The source path and line range let us trace an answer citation back to the file.
The metadata lets later retrieval and policy handling distinguish authoritative
policy from marketing copy, or current material from historical material.

`search_text` deliberately adds document context rather than searching a bare
paragraph without its subject. The `content` field still preserves the section
separately for inspecting exactly what the source says.

## A subtle issue: warnings outside section headings

The old returns policy contains this warning before its first section:

> This version was replaced by version 4 on 1 August 2026. It still applies only to electronics delivered before 1 August 2026.

If we extracted only the table under `[RETv3-2]`, we would lose that warning.
The search result could then show the old 10-day electronics window without
its historical restriction. We carry the document preamble with every section
from that document so the restriction survives chunking.

Preserving this context does not finish policy reasoning. Current-policy
exceptions can also appear in other sections, and some answers need multiple
sources. Phase 7 will handle precedence and applicability when assembling
retrieved evidence. Ingestion retains the source facts and version links.

## What we keep and what we exclude

The corpus contains 84 uniquely identified sections from 21 documents:

- 20 current documents containing 82 sections.
- 1 superseded document containing 2 sections.
- 80 English sections and 4 Hindi sections.

Superseded content stays in the corpus because some historical cases still
need it. Its status remains attached to each chunk. Current status alone does
not establish applicability to a particular order.

The ingestion module reads only `kb/*.md`. It does not read practice questions,
reference answers, customers, orders, support logs, or tool output. Public
catalog facts will be connected to retrieval in a subsequent phase; private
order details will remain behind verified tools.

This separation keeps the evaluation answer key out of retrieved knowledge and
prevents customer records from entering a general document-search corpus.

## Validation and reproducibility

The parser rejects missing/duplicate metadata fields, unsupported document
types/statuses, invalid dates, headings without section IDs, empty sections,
duplicate document/section IDs, missing version-link targets, and unclosed
fenced code blocks. It supports the pack's flat metadata fields and simple
quoted strings, not arbitrary YAML or the entire Markdown specification.

Files are processed in a stable order, and the same inputs produce identical
chunk records and a matching corpus hash. Every saved run gets a unique folder,
so it does not overwrite previous builds. The manifest records source hashes
and a hash of the exact JSONL bytes to help detect stale or changed artifacts.

Tests check the complete return/refund tables, the old-policy warning, Unicode,
source line ranges, duplicate IDs, malformed inputs, fenced headings, stable
outputs, and JSONL round trips. A separate test ensures ingestion reads only
Markdown files inside `kb/`.

## Read the implementation

Start with `KnowledgeChunk` in `src/zentromart/ingestion.py`, then follow:

1. `_metadata`: validate the document header while retaining strings such as `4.0`.
2. `parse_document`: identify sections, preserve context, and record source lines.
3. `build_corpus`: combine documents and enforce global ID/version-link checks.
4. `save_corpus`: export the JSONL corpus and its build manifest.

Next we will give a customer question to keyword search and rank these chunks.
That is when the evidence metrics from Phase 3 begin measuring actual retrieval.

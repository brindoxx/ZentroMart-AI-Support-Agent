"""Check policy preservation, citation provenance, and the retrieval input boundary."""

from datetime import date
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from zentromart.config import PROJECT_ROOT
from zentromart.ingestion import build_corpus, parse_document, save_corpus, summarize_corpus


HEADER = """---
doc_id: TEST-1
title: A policy: details
doc_type: policy
audience: customer
language: en
version: 1.0
effective_from: 2026-08-01
status: current
---
"""
SAMPLE = HEADER + """
# A policy

> This document has limited applicability.

## [TEST-1.1] First section
Keep this body.

| Item | Days |
| --- | --- |
| Electronics | 7 |

## [TEST-1.2] Second section
दूसरा सवाल ₹49
"""


class DocumentParsingTests(unittest.TestCase):
    def test_sections_keep_tables_context_metadata_and_source_lines(self):
        chunks = parse_document(SAMPLE, "kb/test.md")
        self.assertEqual([chunk.section_id for chunk in chunks], ["TEST-1.1", "TEST-1.2"])
        self.assertEqual(chunks[0].metadata.title, "A policy: details")
        self.assertEqual(chunks[0].metadata.version, "1.0")
        self.assertIn("| Electronics | 7 |", chunks[0].content)
        self.assertNotIn("Second section", chunks[0].content)
        self.assertIn("limited applicability", chunks[1].document_context)
        self.assertIn("limited applicability", chunks[1].search_text)
        self.assertIn("दूसरा सवाल ₹49", chunks[1].content)
        for chunk in chunks:
            self.assertEqual(chunk.content, "".join(
                SAMPLE.splitlines(keepends=True)[chunk.line_start - 1:chunk.line_end]
            ).strip())
            self.assertEqual(chunk.source_sha256, hashlib.sha256(SAMPLE.encode()).hexdigest())

    def test_bom_crlf_and_simple_quoted_metadata(self):
        source = "\ufeff" + SAMPLE.replace("version: 1.0", 'version: "1.0"').replace("\n", "\r\n")
        chunks = parse_document(source, "kb/test.md")
        self.assertEqual(chunks[0].metadata.version, "1.0")
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].line_start, parse_document(SAMPLE, "kb/test.md")[0].line_start)

    def test_fenced_headings_are_content_not_new_chunks(self):
        for fence in ("```", "~~~~"):
            text = HEADER + f"\n## [TEST-1] Example\n{fence}\n## [FAKE-1] Example text\n{fence}\nEnd.\n"
            with self.subTest(fence=fence):
                chunks = parse_document(text, "kb/test.md")
                self.assertEqual(len(chunks), 1)
                self.assertIn("[FAKE-1]", chunks[0].content)

    def test_bad_metadata_and_ambiguous_sections_fail_loudly(self):
        invalid = (
            SAMPLE.replace("doc_id: TEST-1\n", ""),
            SAMPLE.replace("status: current", "status: current\nstatus: superseded"),
            SAMPLE.replace("status: current", "status: obsolete"),
            SAMPLE.replace("doc_type: policy", "doc_type: unknown"),
            SAMPLE.replace("effective_from: 2026-08-01", "effective_from: 2026-02-30"),
            SAMPLE.replace("title: A policy: details", "title: |\n  nested block"),
            SAMPLE.replace("[TEST-1.2]", "[TEST-1.1]"),
            SAMPLE.replace("## [TEST-1.2] Second section", "## Missing ID"),
            HEADER + "\n## [EMPTY-1] Empty\n",
            HEADER + "\nNo sections.\n",
            SAMPLE + "\n```\nunclosed code\n",
            "not a metadata header\n" + SAMPLE,
            HEADER.replace("---\n", "", 1),
        )
        for text in invalid:
            with self.subTest(text=text[:60]), self.assertRaises(ValueError):
                parse_document(text, "kb/test.md")


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.dataset = PROJECT_ROOT / "dataset"

    def test_only_kb_markdown_is_read_and_results_are_deterministic(self):
        original = Path.read_bytes
        def guarded_read(path):
            self.assertEqual(path.parent, self.dataset / "kb")
            self.assertEqual(path.suffix, ".md")
            return original(path)
        with patch.object(Path, "read_bytes", guarded_read):
            chunks = build_corpus(self.dataset)
        self.assertEqual(chunks, build_corpus(self.dataset))
        self.assertEqual(len(chunks), 84)
        self.assertEqual(len({chunk.chunk_id for chunk in chunks}), 84)
        summary = summarize_corpus(chunks)
        self.assertEqual(summary["documents"], 21)
        self.assertEqual(summary["documents_by_status"], {"current": 20, "superseded": 1})
        self.assertEqual(summary["chunks_by_status"], {"current": 82, "superseded": 2})
        self.assertEqual(summary["chunks_by_language"], {"en": 80, "hi": 4})

    def test_real_historical_context_and_full_tables_survive(self):
        chunks = {chunk.section_id: chunk for chunk in build_corpus(self.dataset)}
        old = chunks["RETv3-2"]
        self.assertEqual(old.metadata.superseded_by, "POL-RET")
        self.assertIn("electronics delivered before 1 August 2026", old.document_context)
        self.assertEqual(chunks["RET-2"].metadata.supersedes, "POL-RET-v3")
        self.assertIn("| Gift cards and digital codes | Not returnable | `digital` |", chunks["RET-2"].content)
        self.assertIn("Net banking", chunks["REF-2"].content)
        self.assertIn("Bank transfer (NEFT)", chunks["REF-2"].content)
        for chunk in chunks.values():
            lines = (self.dataset / chunk.source).read_text(encoding="utf-8").splitlines()
            self.assertEqual("\n".join(lines[chunk.line_start - 1:chunk.line_end]).strip(), chunk.content)

    def test_duplicate_document_section_and_broken_version_links_are_rejected(self):
        variants = (
            SAMPLE.replace("TEST-1.1", "OTHER-1").replace("TEST-1.2", "OTHER-2"),
            SAMPLE.replace("doc_id: TEST-1", "doc_id: OTHER"),
            SAMPLE.replace("doc_id: TEST-1", "doc_id: OTHER").replace("TEST-1.1", "OTHER-1")
                  .replace("TEST-1.2", "OTHER-2").replace("status: current", "status: current\nsupersedes: MISSING"),
        )
        for second in variants:
            with self.subTest(second=second[:50]), TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "kb").mkdir()
                (root / "kb/one.md").write_text(SAMPLE, encoding="utf-8")
                (root / "kb/two.md").write_text(second, encoding="utf-8")
                with self.assertRaises(ValueError):
                    build_corpus(root)

    def test_saved_corpus_round_trips_unicode_and_matches_manifest_hash(self):
        chunks = parse_document(SAMPLE, "kb/test.md")
        with TemporaryDirectory() as directory:
            output = save_corpus(chunks, Path(directory), date(2026, 10, 20))
            repeated = save_corpus(chunks, Path(directory), date(2026, 10, 20))
            self.assertNotEqual(output, repeated)
            payload = (output / "chunks.jsonl").read_bytes()
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["corpus_sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(payload, (repeated / "chunks.jsonl").read_bytes())
            self.assertIn("दूसरा सवाल ₹49", payload.decode("utf-8"))
            records = [json.loads(line) for line in payload.decode("utf-8").splitlines()]
            self.assertEqual(records, [chunk.to_dict() for chunk in chunks])
            self.assertEqual(manifest["chunks"], 2)


if __name__ == "__main__":
    unittest.main()

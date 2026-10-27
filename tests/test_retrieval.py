"""Verify ranking mechanics, Unicode handling, and separation from private data."""

from dataclasses import replace
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from zentromart.config import PROJECT_ROOT, load_settings
from zentromart.dataset import read_table
from zentromart.evaluation.cases import Case, Target
from zentromart.evaluation.retrieval import evaluate_retrieval
from zentromart.retrieval import BM25Index, SearchDocument, build_indexes, load_search_documents, tokenize


def document(identifier, text, status="current"):
    return SearchDocument(identifier, identifier, text, "kb/test.md", {"doc_type": "policy", "status": status})


class BM25Tests(unittest.TestCase):
    def test_default_factory_does_not_import_optional_semantic_dependencies(self):
        with patch.dict("sys.modules", {"zentromart.semantic": None}):
            indexes = build_indexes([document("A", "refund")], Path("unused"), ("bm25",))
        self.assertEqual(indexes["bm25"].search("refund")[0].document.evidence_id, "A")

    def test_unicode_words_keep_hindi_marks_and_identifier_zeros(self):
        self.assertEqual(tokenize("The REFUND, ELE-0012!"), ("refund", "ele", "0012"))
        self.assertEqual(tokenize("रिफ़ंड कैसे मिलेगा?"), ("रिफ़ंड", "कैसे", "मिलेगा"))
        self.assertEqual(tokenize("No refund, not without photos"), ("no", "refund", "not", "without", "photos"))

    def test_score_matches_hand_calculated_bm25_and_term_contributions(self):
        index = BM25Index([document("A", "refund refund"), document("B", "refund delivery")])
        hits = index.search("refund")
        idf = math.log(1 + (2 - 2 + 0.5) / (2 + 0.5))
        self.assertEqual(hits[0].document.evidence_id, "A")
        self.assertAlmostEqual(hits[0].score, idf * 2 * 2.2 / (2 + 1.2))
        self.assertAlmostEqual(hits[1].score, idf)
        for hit in index.search("refund delivery"):
            self.assertAlmostEqual(hit.score, sum(hit.term_scores.values()))

    def test_frequency_saturates_and_length_normalization_changes_ranking(self):
        index = BM25Index([document("A", "refund"), document("B", "refund refund")], b=0)
        scores = {hit.document.evidence_id: hit.score for hit in index.search("refund")}
        self.assertGreater(scores["B"], scores["A"])
        self.assertLess(scores["B"], 2 * scores["A"])
        long_text = "refund " + "filler " * 30
        hits = BM25Index([document("A", "refund"), document("B", long_text)]).search("refund")
        self.assertEqual(hits[0].document.evidence_id, "A")

    def test_rare_terms_receive_more_weight(self):
        index = BM25Index([document("A", "refund unique"), document("B", "refund common"),
                           document("C", "refund common")])
        hit = index.search("refund unique")[0]
        self.assertGreater(hit.term_scores["unique"], hit.term_scores["refund"])

    def test_no_matches_return_no_fake_zero_score_hits(self):
        index = BM25Index([document("A", "refund policy")])
        for query in ("", "!!!", "the and my", "zzzxxyy"):
            with self.subTest(query=query):
                self.assertEqual(index.search(query), [])

    def test_repeated_query_terms_and_ties_are_deterministic(self):
        docs = [document("B", "refund"), document("A", "refund")]
        index = BM25Index(docs)
        self.assertEqual(index.search("refund"), index.search("refund refund"))
        self.assertEqual([hit.document.evidence_id for hit in index.search("refund")], ["A", "B"])
        self.assertEqual(index.corpus_sha256, BM25Index(list(reversed(docs))).corpus_sha256)
        self.assertEqual(len(index.search("refund", top_k=1)), 1)

    def test_parameters_and_document_keys_are_checked(self):
        for kwargs in ({"k1": -1}, {"k1": math.nan}, {"b": math.inf}, {"b": 1.1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                BM25Index([document("A", "refund")], **kwargs)
        for docs in ([], [document("A", "refund"), document("A", "other")], [document("A", "the")]):
            with self.assertRaises(ValueError):
                BM25Index(docs)
        index = BM25Index([document("A", "refund")])
        for top_k in (0, -1, True, 1.5):
            with self.subTest(top_k=top_k), self.assertRaises(ValueError):
                index.search("refund", top_k)

    def test_keyword_ranking_does_not_silently_enforce_policy_precedence(self):
        index = BM25Index([document("OLD", "refund", "superseded"),
                           document("NEW", "delivery", "current")])
        hit = index.search("refund")[0]
        self.assertEqual(hit.document.evidence_id, "OLD")
        self.assertEqual(hit.to_dict()["metadata"]["status"], "superseded")


class RetrievalIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.root = PROJECT_ROOT / "dataset"

    def test_index_reads_only_kb_and_public_catalog(self):
        original_open = Path.open
        def guarded_open(path, *args, **kwargs):
            allowed = (path.parent == self.root / "kb" and path.suffix == ".md") or path == self.root / "data/products.csv"
            self.assertTrue(allowed, "Retrieval attempted to read a non-public source")
            return original_open(path, *args, **kwargs)
        with patch.object(Path, "open", guarded_open):
            docs = load_search_documents(self.root)
        self.assertEqual(len(docs), 154)
        self.assertEqual(sum(doc.metadata["doc_type"] == "catalog" for doc in docs), 70)
        hits = BM25Index(docs).search("ELE-0012")
        self.assertEqual(hits[0].document.evidence_id, "products.csv:ELE-0012")

    def test_catalog_allowlist_excludes_new_unapproved_columns(self):
        columns, rows = read_table(self.root / "data/products.csv")
        with patch("zentromart.retrieval.read_table", return_value=(
            columns + ["private_field"], [{**row, "private_field": "NEVER_INDEX_THIS"} for row in rows]
        )):
            docs = load_search_documents(self.root)
        self.assertFalse(any("NEVER_INDEX_THIS" in doc.text for doc in docs))

    def test_evaluation_uses_only_queries_and_excludes_no_gold_from_metrics(self):
        expected = Target(("answer",), "en", ("A",), ("SECRET_LABEL",), (), None)
        cases = [[Case("PQ0001", "q1", 1, "refund", expected)],
                 [Case("PQ0002", "q2", 1, "refund", replace(expected, evidence=()))]]
        index = BM25Index([document("A", "refund")])
        with patch("zentromart.evaluation.retrieval.load_cases", return_value=cases):
            report = evaluate_retrieval(load_settings(), index, top_k=1)
        self.assertEqual(report["summary"]["scored_questions"], 1)
        self.assertEqual(report["summary"]["no_gold_questions"], 1)
        self.assertEqual(report["summary"]["metrics"]["retrieval_hit_at_k"]["mean"], 1)
        self.assertIsNone(report["rows"][1]["metrics"]["retrieval_hit_at_k"])
        self.assertNotIn("SECRET_LABEL", json.dumps(report))

    def test_full_evaluation_and_asr_cover_all_questions_without_saving_messages(self):
        index = BM25Index(load_search_documents(self.root))
        for asr in (False, True):
            report = evaluate_retrieval(load_settings(), index, asr=asr)
            self.assertEqual(report["summary"]["questions"], 52)
            self.assertEqual(report["summary"]["scored_questions"], 47)
            self.assertEqual(report["summary"]["no_gold_questions"], 5)
            self.assertFalse(any(row["gold_evidence_not_in_index"] for row in report["rows"]))
            self.assertEqual(set(report["by_language"]), {"en", "hi", "hi-en"})
            _, questions = read_table(self.root / "practice/questions.csv")
            for field in ("question", "asr_text", "reference_answer"):
                self.assertNotIn(questions[0][field], json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()

"""Test vector search/cache/fusion with tiny fake vectors; never download models."""

import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from zentromart.hybrid import HybridIndex
from zentromart.retrieval import BM25Index, SearchDocument, SearchHit

HAS_NUMPY = importlib.util.find_spec("numpy") is not None
if HAS_NUMPY:
    import numpy as np
    from zentromart.semantic import SemanticIndex


def document(identifier, text):
    return SearchDocument(identifier, identifier, text, "kb/test.md", {"doc_type": "policy"})


class FakeEncoder:
    def __init__(self, revision="fake-v1"):
        self.calls = []
        self.revision = revision

    def configuration(self):
        return {"dimensions": 2, "query_prefix": "query: ", "passage_prefix": "passage: ",
                "revision": self.revision}

    def encode(self, texts):
        self.calls.append(texts)
        return np.array([[3, 0] if "return" in text or "back" in text else [0, 4] for text in texts])


@unittest.skipUnless(HAS_NUMPY, "Install .[semantic] to run embedding tests")
class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.docs = [document("A", "clothing returns"), document("B", "refund delay")]

    def test_cosine_search_normalizes_vectors_and_uses_query_passage_prefixes(self):
        encoder = FakeEncoder()
        with TemporaryDirectory() as folder:
            index = SemanticIndex(self.docs, encoder, Path(folder))
            hits = index.search("send it back")
        self.assertEqual(hits[0].document.evidence_id, "A")
        self.assertAlmostEqual(hits[0].score, 1)
        self.assertAlmostEqual(hits[1].score, 0)
        self.assertEqual(hits[0].score_kind, "cosine")
        self.assertEqual(encoder.calls[0], ["passage: clothing returns", "passage: refund delay"])
        self.assertEqual(encoder.calls[1], ["query: send it back"])

    def test_cache_reuses_passage_vectors_and_does_not_store_customer_queries(self):
        with TemporaryDirectory() as folder:
            encoder = FakeEncoder()
            first = SemanticIndex(self.docs, encoder, Path(folder))
            first.search("PRIVATE_QUERY_SENTINEL")
            second_encoder = FakeEncoder()
            second = SemanticIndex(list(reversed(self.docs)), second_encoder, Path(folder))
            self.assertTrue(second.cache_hit)
            self.assertEqual(second_encoder.calls, [])
            np.testing.assert_array_equal(first.matrix, second.matrix)
            for path in Path(folder).rglob("*"):
                if path.is_file():
                    self.assertNotIn(b"PRIVATE_QUERY_SENTINEL", path.read_bytes())

    def test_changed_corpus_or_encoder_revision_builds_a_new_cache(self):
        with TemporaryDirectory() as folder:
            base = Path(folder)
            SemanticIndex(self.docs, FakeEncoder(), base)
            changed_encoder = FakeEncoder("fake-v2")
            changed_model = SemanticIndex(self.docs, changed_encoder, base)
            changed_docs = SemanticIndex([document("A", "other return text"), self.docs[1]], FakeEncoder(), base)
            self.assertFalse(changed_model.cache_hit)
            self.assertFalse(changed_docs.cache_hit)
            self.assertEqual(len(list(base.glob("*/manifest.json"))), 3)

    def test_corrupt_matrix_is_rejected_and_explicit_rebuild_recovers(self):
        with TemporaryDirectory() as folder:
            base = Path(folder)
            SemanticIndex(self.docs, FakeEncoder(), base)
            manifest_path = next(base.glob("*/manifest.json"))
            manifest = json.loads(manifest_path.read_text())
            (manifest_path.parent / manifest["matrix_file"]).write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "rebuild-embeddings"):
                SemanticIndex(self.docs, FakeEncoder(), base)
            rebuilt = SemanticIndex(self.docs, FakeEncoder(), base, rebuild=True)
            self.assertFalse(rebuilt.cache_hit)
            self.assertTrue(SemanticIndex(self.docs, FakeEncoder(), base).cache_hit)

    def test_wrong_shape_zero_and_nonfinite_vectors_are_rejected(self):
        for values in ([[1, 0]], [[0, 0], [1, 0]], [[float("nan"), 0], [1, 0]]):
            class BadEncoder(FakeEncoder):
                def encode(self, texts):
                    return values
            with self.subTest(values=values), TemporaryDirectory() as folder:
                with self.assertRaises(ValueError):
                    SemanticIndex(self.docs, BadEncoder(), Path(folder))

    def test_blank_queries_and_top_k_validation(self):
        with TemporaryDirectory() as folder:
            index = SemanticIndex(self.docs, FakeEncoder(), Path(folder))
            for query in ("", "!!!", "the my"):
                self.assertEqual(index.search(query), [])
            with self.assertRaises(ValueError):
                index.search("refund", 0)


class StubIndex:
    def __init__(self, hits, fingerprint="same-corpus"):
        self.hits = hits
        self.documents = tuple(hit.document for hit in hits)
        self.fingerprint = fingerprint

    def search(self, query, top_k=5):
        return self.hits[:top_k]

    def configuration(self):
        return {"corpus_sha256": self.fingerprint}


class HybridTests(unittest.TestCase):
    def test_fusion_uses_ranks_not_incompatible_raw_scores(self):
        a, b, c = document("A", "a"), document("B", "b"), document("C", "c")
        lexical = StubIndex([SearchHit(a, 10000, {"term": 10000}), SearchHit(b, 1, {"term": 1})])
        semantic = StubIndex([SearchHit(b, 0.8, {}, "cosine"), SearchHit(c, 0.7, {}, "cosine")])
        hit = HybridIndex(lexical, semantic).search("query")[0]
        self.assertEqual(hit.document.evidence_id, "B")
        self.assertAlmostEqual(hit.score, 1 / 62 + 1 / 61)
        self.assertEqual(hit.components["bm25_rank"], 2)
        self.assertEqual(hit.components["semantic_rank"], 1)
        self.assertEqual(hit.score_kind, "rrf")

    def test_incompatible_corpora_and_invalid_parameters_are_rejected(self):
        left = StubIndex([], "one")
        right = StubIndex([], "two")
        with self.assertRaises(ValueError):
            HybridIndex(left, right)
        with self.assertRaises(ValueError):
            HybridIndex(left, left, candidate_k=0)
        with self.assertRaises(ValueError):
            HybridIndex(left, left).search("query", 0)

    def test_fusion_ties_are_stable_and_candidates_are_not_duplicated(self):
        a, b = document("A", "a"), document("B", "b")
        lexical = StubIndex([SearchHit(a, 1, {}), SearchHit(b, 1, {})])
        semantic = StubIndex([SearchHit(b, 1, {}), SearchHit(a, 1, {})])
        hits = HybridIndex(lexical, semantic).search("query")
        self.assertEqual([hit.document.evidence_id for hit in hits], ["A", "B"])


if __name__ == "__main__":
    unittest.main()

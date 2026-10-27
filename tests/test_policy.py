"""Source-grounded precedence and applicability scenarios, not answer-quality scores."""

from dataclasses import replace
from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch

from zentromart.config import PROJECT_ROOT
from zentromart.policy import PolicyContext, PolicyEngine
from zentromart.retrieval import SearchHit, corpus_fingerprint, load_search_documents


REFERENCE_DATE = date(2026, 10, 20)


class FixedRanking:
    """Control retrieval order while keeping all real documents available for policy links."""

    def __init__(self, documents, ranking):
        self.documents = tuple(sorted(documents, key=lambda doc: doc.evidence_id))
        self.ranking = ranking
        self.lookup = {doc.evidence_id: doc for doc in self.documents}

    def configuration(self):
        return {"corpus_sha256": corpus_fingerprint(self.documents)}

    def search(self, query, top_k=5):
        return [SearchHit(self.lookup[identifier], 1000 - rank, {})
                for rank, identifier in enumerate(self.ranking[:top_k])]


class PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = load_search_documents(PROJECT_ROOT / "dataset")

    def engine(self, ranking=(), documents=None):
        return PolicyEngine(FixedRanking(documents or self.documents, ranking), REFERENCE_DATE)

    def entries(self, bundle):
        return {entry["evidence_id"]: entry for entry in bundle["evidence"]}

    def test_refund_policy_is_added_above_a_high_scoring_general_faq(self):
        bundle = self.engine(("FAQ-1",)).assemble("refund timing")
        ids = [entry["evidence_id"] for entry in bundle["evidence"]]
        self.assertLess(ids.index("REF-2"), ids.index("FAQ-1"))
        self.assertLess(ids.index("REF-3"), ids.index("FAQ-1"))
        self.assertEqual(self.entries(bundle)["REF-2"]["origins"], ["policy_dependency"])
        self.assertIsNone(self.entries(bundle)["REF-2"]["retrieval_score"])
        self.assertNotIn("RET-2", ids)  # Unrelated policies are not globally promoted.

    def test_marketing_and_hindi_faq_cannot_override_policies(self):
        for ranked, expected in (("MKT-1", "PLS-2"), ("FAQH-2", "REF-2"), ("FAQH-3", "DWM-3")):
            with self.subTest(ranked=ranked):
                bundle = self.engine((ranked,)).assemble("policy question")
                ids = [entry["evidence_id"] for entry in bundle["evidence"]]
                self.assertLess(ids.index(expected), ids.index(ranked))

    def test_unknown_historical_context_does_not_unlock_superseded_sources(self):
        for context in (PolicyContext(), PolicyContext("return_window"),
                        PolicyContext("return_window", category="electronics")):
            with self.subTest(context=context):
                bundle = self.engine(("RETv3-2", "RETv3-6")).assemble("return policy", context)
                self.assertNotIn("RETv3-2", self.entries(bundle))
                self.assertNotIn("RETv3-6", self.entries(bundle))
                if context.topic == "return_window":
                    self.assertEqual(bundle["resolution"], "needs_context")
                    self.assertTrue(bundle["required_context"])

    def test_electronics_historical_exception_has_exact_date_boundaries(self):
        for delivered, allowed in ((date(2026, 3, 1), True), (date(2026, 7, 31), True),
                                   (date(2026, 8, 1), False), (date(2026, 10, 20), False)):
            with self.subTest(delivered=delivered):
                context = PolicyContext("return_window", category="electronics", delivered_on=delivered)
                bundle = self.engine(("RETv3-2", "RET-2", "RETv3-6")).assemble("electronics returns", context)
                entries = self.entries(bundle)
                self.assertEqual("RETv3-2" in entries, allowed)
                self.assertNotIn("RETv3-6", entries)
                if allowed:
                    self.assertEqual(bundle["evidence"][0]["evidence_id"], "RETv3-2")
                    self.assertEqual(entries["RET-2"]["role"], "general_background")
                    self.assertIn("RET-3", entries)

    def test_historical_window_does_not_revive_old_pickup_fees_or_other_categories(self):
        contexts = (
            PolicyContext("return_fee", category="electronics", delivered_on=date(2026, 7, 31)),
            PolicyContext("return_window", category="fashion", delivered_on=date(2026, 7, 31), placed_on=date(2026, 7, 20)),
        )
        for context in contexts:
            with self.subTest(context=context):
                bundle = self.engine(("RETv3-2", "RETv3-6")).assemble("return pickup", context)
                self.assertNotIn("RETv3-2", self.entries(bundle))
                self.assertNotIn("RETv3-6", self.entries(bundle))
                self.assertIn("RET-6", self.entries(bundle))

    def test_delivery_before_supplied_policy_history_requires_review(self):
        context = PolicyContext("return_window", category="electronics", delivered_on=date(2026, 2, 28))
        bundle = self.engine(("RETv3-2",)).assemble("historical return", context)
        self.assertEqual(bundle["resolution"], "review_required")
        self.assertEqual(bundle["applicability"]["historical_electronics_window"], "unsupported_date_range")
        self.assertNotIn("RETv3-2", self.entries(bundle))

    def test_festive_window_uses_placement_date_and_inclusive_boundaries(self):
        for placed, expected in ((date(2026, 9, 30), "not_applicable"),
                                 (date(2026, 10, 1), "applicable"),
                                 (date(2026, 10, 15), "applicable"),
                                 (date(2026, 10, 16), "not_applicable")):
            context = PolicyContext("return_window", category="fashion", placed_on=placed,
                                    delivered_on=date(2026, 10, 20))
            with self.subTest(placed=placed):
                bundle = self.engine().assemble("fashion returns", context)
                self.assertEqual(bundle["applicability"]["festive_fashion_extension"], expected)
                self.assertIn("RET-8", self.entries(bundle))

    def test_missing_fashion_placement_date_is_conditional_not_a_guessed_window(self):
        bundle = self.engine().assemble("fashion returns", PolicyContext("return_window", category="fashion"))
        self.assertEqual(bundle["required_context"], ["placed_on"])
        self.assertEqual(self.entries(bundle)["RET-8"]["role"], "conditional_policy")

    def test_marketplace_assured_badge_is_limited_by_seller_policy(self):
        context = PolicyContext("warranty", sku="ELE-0004")
        bundle = self.engine(("WAR-2", "products.csv:ELE-0004")).assemble("Assured warranty", context)
        self.assertEqual(bundle["applicability"]["marketplace_assured"], "marketplace_assured_excluded")
        ids = [entry["evidence_id"] for entry in bundle["evidence"]]
        self.assertLess(ids.index("MKS-3"), ids.index("WAR-2"))
        self.assertEqual(self.entries(bundle)["WAR-2"]["role"], "limited_by_marketplace_exception")
        self.assertEqual(self.entries(bundle)["products.csv:ELE-0004"]["role"], "catalog_fact")

    def test_unknown_seller_is_not_assumed_to_be_zentromart(self):
        bundle = self.engine().assemble("warranty", PolicyContext("warranty"))
        self.assertEqual(bundle["applicability"]["marketplace_assured"], "conditional_on_seller")
        self.assertIn("MKS-3", self.entries(bundle))

    def test_unknown_sku_category_conflicts_and_invalid_dates_fail(self):
        bad_contexts = (
            PolicyContext("unknown"), PolicyContext(category="unknown"),
            PolicyContext(sku="ELE-9999"), PolicyContext(sku="not-a-sku"),
            PolicyContext(sku="ELE-0004", category="fashion"),
            PolicyContext(delivered_on=date(2026, 10, 21)),
            PolicyContext(delivered_on=date(2026, 8, 1), placed_on=date(2026, 8, 2)),
        )
        for context in bad_contexts:
            with self.subTest(context=context), self.assertRaises(ValueError):
                self.engine().assemble("question", context)

    def test_not_yet_effective_dependency_cannot_be_replaced_by_faq(self):
        documents = [replace(doc, metadata={**doc.metadata, "effective_from": "2026-11-01"})
                     if doc.evidence_id == "REF-2" else doc for doc in self.documents]
        bundle = self.engine(("FAQ-1",), documents).assemble("refund")
        self.assertEqual(bundle["resolution"], "review_required")
        self.assertNotIn("REF-2", self.entries(bundle))
        self.assertIn({"evidence_id": "REF-2", "reason": "document_not_yet_effective"}, bundle["excluded"])

    def test_topic_anchors_work_without_matching_query_terms(self):
        bundle = self.engine().assemble("zzzxxyy", PolicyContext("refunds"))
        self.assertIn("REF-2", self.entries(bundle))
        self.assertEqual(self.entries(bundle)["REF-2"]["origins"], ["topic_anchor"])

    def test_no_usable_evidence_requires_review_not_an_invented_answer(self):
        bundle = self.engine().assemble("zzzxxyy")
        self.assertEqual(bundle["evidence"], [])
        self.assertEqual(bundle["resolution"], "review_required")

    def test_deterministic_bundle_does_not_read_private_tables_or_eval_labels(self):
        engine = self.engine(("FAQ-1", "RETv3-2"))
        with patch.object(Path, "open", side_effect=AssertionError("Policy engine attempted file access")):
            first = engine.assemble("refund query", PolicyContext("refunds"))
            second = engine.assemble("refund query", PolicyContext("refunds"))
        self.assertEqual(first, second)
        self.assertTrue(first["dependency_links"])

    def test_changed_rule_format_or_missing_sources_fail_explicitly(self):
        documents = [replace(doc, text=doc.text.replace("August", "UnknownMonth"))
                     if doc.evidence_id == "RET-3" else doc for doc in self.documents]
        with self.assertRaisesRegex(ValueError, "applicability adapter"):
            self.engine(documents=documents)
        with self.assertRaisesRegex(ValueError, "Required policy evidence is missing"):
            self.engine(documents=[doc for doc in self.documents if doc.evidence_id != "RET-3"])

    def test_mismatched_corpus_and_invalid_top_k_are_rejected(self):
        index = FixedRanking(self.documents, ())
        with patch.object(index, "configuration", return_value={"corpus_sha256": "wrong"}):
            with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
                PolicyEngine(index, REFERENCE_DATE)
        with self.assertRaisesRegex(ValueError, "top-k must be positive"):
            self.engine().assemble("refund", top_k=0)


if __name__ == "__main__":
    unittest.main()

"""Dataset-specific evidence precedence and explicitly scoped applicability.

This prepares evidence for the future generator; it neither authenticates a
caller nor calculates deadlines. Topics/facts are supplied by application code,
not inferred from evaluation labels or private order tables.
"""

from dataclasses import dataclass
from datetime import date
import re

from .retrieval import SearchDocument, SearchIndex, corpus_fingerprint


TOPIC_ANCHORS = {
    "general": (),
    "return_window": ("RET-2", "RET-3"),
    "return_fee": ("RET-6", "PLS-2"),
    "refunds": ("REF-1", "REF-2", "REF-3", "KB-00.3"),
    "membership": ("PLS-1", "PLS-2"),
    "delivery": ("DEL-1", "DEL-2", "DEL-4", "DEL-5"),
    "cancellations": ("CAN-1", "CAN-2", "CAN-3"),
    "damage": ("DWM-1", "DWM-2", "DWM-3", "DWM-5", "ESC-1"),
    "warranty": ("WAR-1", "WAR-2", "WAR-3", "MKS-3"),
    "coupons": ("CPN-1", "CPN-2", "REF-4"),
    "pickup": ("RVP-2", "RET-4", "RET-6"),
}
# Curated, source-grounded section relationships, not practice-answer boosts.
DEPENDENCIES = {
    "MKT-1": ("PLS-1", "PLS-2"),
    "FAQ-1": ("REF-2", "REF-3"), "FAQ-2": ("RET-2", "RET-3", "RET-5"),
    "FAQ-3": ("DEL-2",), "FAQ-4": ("ESC-1", "ESC-2"), "FAQ-5": ("DEL-5",),
    "FAQH-1": ("CAN-1", "CAN-2"), "FAQH-2": ("REF-2", "REF-3"),
    "FAQH-3": ("DWM-1", "DWM-2", "DWM-3"), "FAQH-4": ("PLS-2",),
    "RET-2": ("RET-3", "RET-8"), "RET-7": ("REF-1", "REF-2", "PLS-2"),
    "RETv3-2": ("RET-2", "RET-3"), "RETv3-6": ("RET-6",),
    "RVP-1": ("RET-4", "RET-6"), "TRK-1": ("DEL-3", "REF-1"),
    "TRK-2": ("DWM-1",), "CAN-2": ("REF-1", "RET-2"),
    "CAN-4": ("REF-4",), "CPN-3": ("REF-4",),
    "WAR-2": ("MKS-3",), "MKS-3": ("WAR-1",),
}
AUTHORITY = {"policy": 0, "agent_guide": 1, "help": 2, "faq": 3, "marketing": 4}
CATEGORIES = frozenset({"electronics", "fashion", "home_kitchen", "beauty_sealed",
                        "books_media", "grocery", "innerwear", "digital"})
MONTHS = {name: i for i, name in enumerate(
    "January February March April May June July August September October November December".split(), 1)}


@dataclass(frozen=True)
class PolicyContext:
    topic: str = "general"
    category: str | None = None
    sku: str | None = None
    delivered_on: date | None = None
    placed_on: date | None = None


class PolicyEngine:
    def __init__(self, index: SearchIndex, reference_date: date):
        self.index, self.reference_date = index, reference_date
        self.documents = {doc.evidence_id: doc for doc in index.documents}
        if corpus_fingerprint(tuple(sorted(index.documents, key=lambda doc: doc.evidence_id))) != index.configuration()["corpus_sha256"]:
            raise ValueError("Policy evidence corpus fingerprint mismatch")
        self._require("KB-00.1")
        # Decode these date boundaries from their policy sources, not the machine clock.
        historical = self._require("RET-3").text
        match = re.search(r"From \*\*(\d{1,2}) ([A-Za-z]+) (\d{4})\*\*", historical)
        if not match or match[2] not in MONTHS or "delivered before" not in historical:
            raise ValueError("RET-3 historical rule format changed; review the applicability adapter")
        self.cutoff = date(int(match[3]), MONTHS[match[2]], int(match[1]))
        self.old_start = date.fromisoformat(self._require("RETv3-2").metadata["effective_from"])
        current_metadata = self._require("RET-3").metadata
        old_metadata = self._require("RETv3-2").metadata
        if (old_metadata.get("superseded_by") != current_metadata.get("doc_id") or
                current_metadata.get("supersedes") != old_metadata.get("doc_id")):
            raise ValueError("Historical version links changed; review the applicability adapter")
        for identifier in ("KB-00.1", "RET-3", "RET-8"):
            metadata = self._require(identifier).metadata
            if metadata.get("status") != "current" or date.fromisoformat(metadata["effective_from"]) > reference_date:
                raise ValueError("Applicability rule sources must be current and effective on the reference date")
        festive = self._require("RET-8").text
        match = re.search(r"placed between (\d{1,2}) ([A-Za-z]+) and (\d{1,2}) ([A-Za-z]+) (\d{4})", festive)
        if not match or match[2] not in MONTHS or match[4] not in MONTHS:
            raise ValueError("RET-8 festive rule format changed; review the applicability adapter")
        self.festive_start = date(int(match[5]), MONTHS[match[2]], int(match[1]))
        self.festive_end = date(int(match[5]), MONTHS[match[4]], int(match[3]))

    def _require(self, identifier: str) -> SearchDocument:
        if identifier not in self.documents:
            raise ValueError(f"Required policy evidence is missing: {identifier}")
        return self.documents[identifier]

    def _context(self, context: PolicyContext) -> tuple[str | None, SearchDocument | None]:
        if context.topic not in TOPIC_ANCHORS or (context.category is not None and context.category not in CATEGORIES):
            raise ValueError("Unknown policy topic or product category")
        for value in (context.delivered_on, context.placed_on):
            if value is not None and (type(value) is not date or value > self.reference_date):
                raise ValueError("Scenario dates must be dates on or before the dataset reference date")
        if context.placed_on and context.delivered_on and context.placed_on > context.delivered_on:
            raise ValueError("Order placement cannot follow delivery")
        product = None
        category = context.category
        if context.sku:
            if not re.fullmatch(r"[A-Z]{3}-[0-9]{4}", context.sku):
                raise ValueError("SKU must use a public catalog identifier such as ELE-0012")
            product = self._require(f"products.csv:{context.sku}")
            if product.metadata.get("doc_type") != "catalog":
                raise ValueError("SKU does not identify public catalog evidence")
            row = dict(line.split(": ", 1) for line in product.text.splitlines() if ": " in line)
            actual = row.get("return_category")
            if actual not in CATEGORIES or (category and category != actual):
                raise ValueError("Product category is missing or conflicts with the public catalog")
            category = actual
        return category, product

    def validate_context(self, context: PolicyContext) -> str | None:
        """Validate public scenario claims and return the catalog-resolved category."""
        return self._context(context)[0]

    def assemble(self, query: str, context: PolicyContext = PolicyContext(), top_k: int = 5) -> dict:
        if top_k < 1:
            raise ValueError("top-k must be positive")
        category, product = self._context(context)
        raw = self.index.search(query, top_k)
        missing, notes = [], []
        historical = "not_applicable"
        festive = "not_evaluated"
        if context.topic == "return_window":
            if category is None:
                missing.append("category")
                historical = festive = "needs_context"
            elif category == "electronics":
                if context.delivered_on is None:
                    missing.append("delivered_on")
                    historical = "needs_context"
                elif context.delivered_on < self.old_start:
                    historical = "unsupported_date_range"
                    notes.append("Delivery predates the supplied historical returns policy; human review is required.")
                elif context.delivered_on < self.cutoff:
                    historical = "applicable"
            elif category == "fashion":
                if context.placed_on is None:
                    missing.append("placed_on")
                    festive = "needs_context"
                else:
                    festive = ("applicable" if self.festive_start <= context.placed_on <= self.festive_end
                               else "not_applicable")
        historical_allowed = historical == "applicable"
        anchors = list(TOPIC_ANCHORS[context.topic])
        if historical_allowed:
            anchors = ["RETv3-2", "RET-3", "RET-2"]
        if context.topic == "return_window" and category in {None, "fashion"}:
            anchors.append("RET-8")
        seller_exception = "not_evaluated"
        if context.topic == "warranty":
            seller_exception = "conditional_on_seller"
            if product:
                row = dict(line.split(": ", 1) for line in product.text.splitlines() if ": " in line)
                if row.get("fulfilled_by") != "ZentroMart":
                    seller_exception = "marketplace_assured_excluded"
                    anchors = ["MKS-3", "WAR-1", "WAR-3", "WAR-2"]
                else:
                    seller_exception = "not_marketplace"
        if product:
            anchors.append(product.evidence_id)
        queue = [(hit.document.evidence_id, "retrieved") for hit in raw]
        queue.extend((identifier, "topic_anchor") for identifier in anchors)
        candidates, origins, links = {}, {}, []
        while queue:
            identifier, origin = queue.pop(0)
            if identifier in candidates:
                origins[identifier].add(origin)
                continue
            candidates[identifier] = self._require(identifier)
            origins[identifier] = {origin}
            for companion in DEPENDENCIES.get(identifier, ()):
                links.append({"from": identifier, "to": companion, "reason": "policy_dependency"})
                queue.append((companion, "policy_dependency"))

        ranks = {hit.document.evidence_id: rank for rank, hit in enumerate(raw, 1)}
        scores = {hit.document.evidence_id: hit.score for hit in raw}
        score_kinds = {hit.document.evidence_id: hit.score_kind for hit in raw}
        excluded, evidence = [], []
        for identifier, doc in candidates.items():
            metadata = doc.metadata
            reason = None
            if metadata.get("doc_type") != "catalog":
                if date.fromisoformat(metadata["effective_from"]) > self.reference_date:
                    reason = "document_not_yet_effective"
                elif metadata["status"] == "superseded" and not (identifier == "RETv3-2" and historical_allowed):
                    reason = "superseded_outside_explicit_historical_exception"
            if reason:
                excluded.append({"evidence_id": identifier, "reason": reason})
                continue
            role = "supporting_reference"
            if metadata.get("doc_type") == "catalog":
                role = "catalog_fact"
            elif metadata.get("doc_type") == "policy":
                role = "policy_evidence"
            if identifier in anchors and metadata.get("doc_type") == "policy":
                role = "topic_policy"
            if identifier == "RETv3-2" and historical_allowed:
                role = "governing_historical_window"
            elif identifier == "RET-2" and historical_allowed:
                role = "general_background"
            if context.topic == "return_window" and missing and identifier in {"RET-2", "RET-8"}:
                role = "conditional_policy"
            if seller_exception == "marketplace_assured_excluded" and identifier == "WAR-2":
                role = "limited_by_marketplace_exception"
            if historical == "unsupported_date_range" and identifier == "RET-2":
                role = "general_background"
            evidence.append({"evidence_id": identifier, "role": role,
                             "authority_order": AUTHORITY.get(metadata.get("doc_type")),
                             "origins": sorted(origins[identifier]), "retrieval_rank": ranks.get(identifier),
                             "retrieval_score": scores.get(identifier), "source": doc.source,
                             "retrieval_score_kind": score_kinds.get(identifier),
                             "metadata": metadata, "text": doc.text})
        # Order only the retrieved passages plus explicit topic/dependency sources.
        # Do not globally promote unrelated policies from a larger candidate pool.
        priority = {identifier: rank for rank, identifier in enumerate(anchors)}
        evidence.sort(key=lambda item: (
            0 if item["role"] == "governing_historical_window" else 1,
            item["authority_order"] if item["authority_order"] is not None else 5,
            priority.get(item["evidence_id"], len(priority)),
            item["retrieval_rank"] or 1000, item["evidence_id"],
        ))
        allowed = {item["evidence_id"] for item in evidence}
        required_policy_ids = set(anchors) | {
            link["to"] for link in links
            if self.documents[link["to"]].metadata.get("doc_type") == "policy"
        }
        missing_anchors = sorted(required_policy_ids - allowed)
        review = historical == "unsupported_date_range" or bool(missing_anchors) or not evidence
        if not evidence:
            notes.append("No usable evidence is available; do not invent an answer.")
        if missing_anchors:
            notes.append("Required topic evidence is unavailable; do not substitute a lower-authority source.")
        if "MKS-3" in allowed:
            notes.append("Catalog badges cannot override the marketplace Assured exclusion in MKS-3.")
        if "PLS-2" in allowed:
            notes.append("Plus does not extend return windows, eligibility, or post-initiation refund timelines (PLS-2).")
        notes.append("This is evidence preparation, not identity verification, deadline calculation, or a generated answer.")
        return {
            "schema_version": 1, "rule_version": "zentromart-policy-v1",
            "reference_date": self.reference_date.isoformat(), "topic": context.topic,
            "index": self.index.configuration(),
            "retrieved_evidence": [hit.document.evidence_id for hit in raw],
            "resolution": "review_required" if review else ("needs_context" if missing else "evidence_prepared"),
            "required_context": missing,
            "applicability": {"historical_electronics_window": historical,
                              "festive_fashion_extension": festive,
                              "marketplace_assured": seller_exception},
            "rule_sources": ["KB-00.1", "RET-3", "RET-8", "MKS-3", "PLS-2"],
            "evidence": evidence, "excluded": excluded, "dependency_links": links,
            "notes": notes,
        }

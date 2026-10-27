"""Fuse keyword and semantic ranks without adding incomparable raw scores."""

from .retrieval import SearchHit, SearchIndex


class HybridIndex:
    def __init__(self, lexical: SearchIndex, semantic: SearchIndex,
                 candidate_k: int = 20, rank_constant: int = 60):
        if candidate_k < 1 or rank_constant < 1:
            raise ValueError("Candidate depth and rank constant must be positive")
        if lexical.configuration()["corpus_sha256"] != semantic.configuration()["corpus_sha256"]:
            raise ValueError("Hybrid retrievers must use the same evidence corpus")
        self.lexical, self.semantic = lexical, semantic
        self.documents = lexical.documents
        self.candidate_k, self.rank_constant = candidate_k, rank_constant

    def configuration(self) -> dict:
        return {"algorithm": "hybrid", "fusion": "equal-weight reciprocal rank fusion",
                "candidate_k": self.candidate_k, "rank_constant": self.rank_constant,
                "candidate_rule": "max(candidate_k, requested_top_k)",
                "document_count": len(self.documents),
                "corpus_sha256": self.lexical.configuration()["corpus_sha256"],
                "lexical": self.lexical.configuration(), "semantic": self.semantic.configuration()}

    def search(self, query: str, top_k: int = 5) -> list[SearchHit]:
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            raise ValueError("top-k must be a positive integer")
        depth = max(top_k, self.candidate_k)
        candidates = {}
        for name, index in (("bm25", self.lexical), ("semantic", self.semantic)):
            for rank, hit in enumerate(index.search(query, depth), 1):
                item = candidates.setdefault(hit.document.evidence_id, {
                    "document": hit.document, "score": 0.0, "terms": {}, "components": {}})
                item["score"] += 1 / (self.rank_constant + rank)
                item["components"][f"{name}_rank"] = rank
                item["components"][f"{name}_score"] = hit.score
                if name == "bm25":
                    item["terms"] = hit.term_scores
        hits = [SearchHit(item["document"], item["score"], item["terms"], "rrf", item["components"])
                for item in candidates.values()]
        return sorted(hits, key=lambda hit: (-hit.score, hit.document.evidence_id))[:top_k]

"""Small, inspectable BM25 baseline over policy sections and the public catalog.

No evaluation labels or private order/customer tables are read here. This uses
positive smoothed IDF and explicit length normalization, not a learned model.
"""

from collections import Counter
from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from pathlib import Path
import unicodedata
from typing import Protocol
from collections.abc import Mapping
from types import MappingProxyType

from .dataset import read_table, require_columns
from .ingestion import build_corpus


STOP_WORDS = frozenset(
    "a an the is are was were be been being i me my we our you your it its this that "
    "these those do does did can could would should please and or of to in on at for "
    "with from by as am have has had".split()
)
TOKENIZER_VERSION = "nfkc_casefold_unicode_words_english_stopwords_v1"


def tokenize(text: str) -> tuple[str, ...]:
    """Keep Unicode combining marks attached to their word, including Hindi matras.

    Hyphens/underscores/punctuation split words. Numeric identifiers retain zeros.
    No stemming, translation, transliteration, or semantic expansion is applied.
    """
    normalized = unicodedata.normalize("NFKC", text).casefold()
    words, current = [], []
    for char in normalized:
        category = unicodedata.category(char)
        if category[0] in {"L", "N"} or (category[0] == "M" and current):
            current.append(char)
        elif current:
            words.append("".join(current))
            current = []
    if current:
        words.append("".join(current))
    return tuple(word for word in words if word not in STOP_WORDS)


@dataclass(frozen=True)
class SearchDocument:
    evidence_id: str
    title: str
    text: str
    source: str
    metadata: Mapping[str, str | int | None]

    def __post_init__(self):
        copied = dict(self.metadata)
        if any(not isinstance(key, str) or type(value) not in (str, int, type(None)) for key, value in copied.items()):
            raise TypeError("Search metadata must contain scalar string/integer/null values")
        object.__setattr__(self, "metadata", MappingProxyType(copied))

    def to_dict(self):
        return {"evidence_id": self.evidence_id, "title": self.title, "text": self.text,
                "source": self.source, "metadata": dict(self.metadata)}

    def __reduce__(self):
        # Streamlit's public-data cache uses pickle; mappingproxy itself is not picklable.
        return (type(self), (self.evidence_id, self.title, self.text, self.source, dict(self.metadata)))

    def __deepcopy__(self, memo):
        return self  # All fields, including metadata values, are immutable scalars.


@dataclass(frozen=True)
class SearchHit:
    document: SearchDocument
    score: float
    term_scores: dict[str, float]
    score_kind: str = "bm25"
    components: dict[str, float | int | None] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"evidence_id": self.document.evidence_id, "score": self.score,
                "title": self.document.title, "source": self.document.source,
                "metadata": dict(self.document.metadata), "matched_terms": self.term_scores,
                "text": self.document.text, "score_kind": self.score_kind,
                "components": self.components}


class SearchIndex(Protocol):
    documents: tuple[SearchDocument, ...]

    def search(self, query: str, top_k: int = 5) -> list[SearchHit]: ...
    def configuration(self) -> dict: ...


def prepare_documents(documents: list[SearchDocument]) -> tuple[SearchDocument, ...]:
    if not documents or len({doc.evidence_id for doc in documents}) != len(documents):
        raise ValueError("Search needs nonempty documents with unique evidence IDs")
    if any(not doc.evidence_id.strip() or not doc.text.strip() for doc in documents):
        raise ValueError("Evidence IDs and document text must be nonempty")
    return tuple(sorted(documents, key=lambda doc: doc.evidence_id))


def corpus_fingerprint(documents: tuple[SearchDocument, ...]) -> str:
    payload = json.dumps([doc.to_dict() for doc in documents], sort_keys=True,
                         ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_search_documents(dataset_dir: Path) -> list[SearchDocument]:
    """Adapt the 84 sections and 70 public catalog rows to one search interface."""
    documents = []
    for chunk in build_corpus(dataset_dir):
        documents.append(SearchDocument(
            evidence_id=chunk.section_id, title=chunk.section_title,
            text=chunk.search_text, source=chunk.source,
            metadata={**asdict(chunk.metadata), "source_sha256": chunk.source_sha256,
                      "line_start": chunk.line_start, "line_end": chunk.line_end},
        ))
    catalog_path = dataset_dir / "data/products.csv"
    if catalog_path.is_symlink() or not catalog_path.resolve().is_relative_to(dataset_dir.resolve()):
        raise ValueError("Catalog source must remain inside the dataset directory")
    columns, rows = read_table(catalog_path)
    require_columns(columns, ("sku", "title", "brand", "return_category", "price_inr", "fulfilled_by",
                              "assured", "warranty_months", "description"), "products.csv")
    # Explicit allowlist: adding a new CSV column must not silently add it to search.
    public_fields = ("sku", "title", "brand", "return_category", "price_inr", "fulfilled_by",
                     "assured", "warranty_months", "description")
    catalog_hash = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
    seen = set()
    for row in rows:
        if not row["sku"].strip() or row["sku"] in seen:
            raise ValueError("Public catalog SKUs must be nonempty and unique")
        seen.add(row["sku"])
        documents.append(SearchDocument(
            evidence_id=f"products.csv:{row['sku']}", title=row["title"],
            text="\n".join(f"{name}: {row[name]}" for name in public_fields),
            source="data/products.csv",
            metadata={"doc_type": "catalog", "source_sha256": catalog_hash},
        ))
    return documents


class BM25Index:
    """BM25 with default k1=1.2, b=0.75; scores are not confidence probabilities."""

    def __init__(self, documents: list[SearchDocument], k1: float = 1.2, b: float = 0.75):
        if not math.isfinite(k1) or k1 < 0 or not math.isfinite(b) or not 0 <= b <= 1:
            raise ValueError("BM25 requires finite k1 >= 0 and 0 <= b <= 1")
        self.documents = prepare_documents(documents)
        self.k1, self.b = k1, b
        self._frequencies = tuple(Counter(tokenize(doc.text)) for doc in self.documents)
        self._lengths = tuple(sum(counts.values()) for counts in self._frequencies)
        self.average_length = sum(self._lengths) / len(self.documents)
        if not self.average_length:
            raise ValueError("Search corpus contains no searchable tokens")
        document_frequency = Counter(term for counts in self._frequencies for term in counts)
        self._idf = {term: math.log1p((len(self.documents) - count + 0.5) / (count + 0.5))
                     for term, count in document_frequency.items()}
        self.corpus_sha256 = corpus_fingerprint(self.documents)

    def configuration(self) -> dict:
        return {"algorithm": "bm25", "k1": self.k1, "b": self.b,
                "tokenizer": TOKENIZER_VERSION, "query_terms": "unique",
                "document_count": len(self.documents), "average_document_tokens": self.average_length,
                "corpus_sha256": self.corpus_sha256,
                "idf": "log(1 + (N - df + 0.5) / (df + 0.5))",
                "tf": "tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl))"}

    def search(self, query: str, top_k: int = 5) -> list[SearchHit]:
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            raise ValueError("top-k must be a positive integer")
        terms = sorted(set(tokenize(query)) & self._idf.keys())
        hits = []
        if not terms:
            return hits
        for doc, frequencies, length in zip(self.documents, self._frequencies, self._lengths):
            normalization = self.k1 * (1 - self.b + self.b * length / self.average_length)
            contributions = {
                term: self._idf[term] * frequencies[term] * (self.k1 + 1) /
                (frequencies[term] + normalization)
                for term in terms if frequencies[term]
            }
            if contributions:
                hits.append(SearchHit(doc, sum(contributions.values()), contributions))
        return sorted(hits, key=lambda hit: (-hit.score, hit.document.evidence_id))[:top_k]


def build_indexes(documents: list[SearchDocument], artifacts_dir: Path,
                  methods: tuple[str, ...], offline: bool = False,
                  rebuild: bool = False) -> dict[str, SearchIndex]:
    """Build shared components once; BM25 never imports optional model libraries."""
    if not methods or not set(methods) <= {"bm25", "semantic", "hybrid"}:
        raise ValueError("Unknown retrieval method")
    lexical = BM25Index(documents)
    indexes = {"bm25": lexical}
    if set(methods) & {"semantic", "hybrid"}:
        from .semantic import E5Encoder, SemanticIndex
        semantic = SemanticIndex(documents, E5Encoder(artifacts_dir / "models", offline),
                                 artifacts_dir / "embeddings", rebuild=rebuild)
        indexes["semantic"] = semantic
        if "hybrid" in methods:
            from .hybrid import HybridIndex
            indexes["hybrid"] = HybridIndex(lexical, semantic)
    return {method: indexes[method] for method in methods}

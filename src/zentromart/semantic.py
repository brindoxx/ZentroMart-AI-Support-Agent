"""Local multilingual E5 embeddings, cosine search, and validated document caches."""

import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
from uuid import uuid4

try:
    import numpy as np
except ImportError:
    raise ValueError('Install semantic dependencies: python -m pip install -e ".[semantic]"') from None

from .retrieval import SearchDocument, SearchHit, corpus_fingerprint, prepare_documents, tokenize


MODEL_ID = "intfloat/multilingual-e5-small"
MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"


class E5Encoder:
    """Lazy CPU-only model; token=False disables implicit use of saved HF tokens."""

    model_id, revision, dimensions = MODEL_ID, MODEL_REVISION, 384
    query_prefix, passage_prefix, batch_size = "query: ", "passage: ", 16
    safetensors = True
    pooling = "model-defined mean pooling"

    def __init__(self, model_cache: Path, offline: bool = False):
        self.model_cache, self.offline = model_cache, offline
        self._model = None

    def configuration(self) -> dict:
        try:
            libraries = {name: version(name) for name in
                         ("sentence-transformers", "transformers", "torch", "numpy")}
        except Exception:
            raise ValueError('Install semantic dependencies: python -m pip install -e ".[semantic]"') from None
        return {"model": self.model_id, "revision": self.revision, "dimensions": self.dimensions,
                "max_sequence_length": 512, "device": "cpu", "dtype": "float32",
                "query_prefix": self.query_prefix, "passage_prefix": self.passage_prefix,
                "batch_size": self.batch_size, "cpu_threads": min(4, os.cpu_count() or 1),
                "pooling": self.pooling, "normalized": True,
                "libraries": libraries}

    def encode(self, texts: list[str]):
        if self._model is None:
            from huggingface_hub import snapshot_download
            from sentence_transformers import SentenceTransformer
            import torch
            # Bound CPU parallelism so a small corpus does not oversubscribe the machine.
            torch.set_num_threads(min(4, os.cpu_count() or 1))
            if not self.safetensors and tuple(int(x) for x in torch.__version__.split('+')[0].split('.')[:2]) < (2, 6):
                raise ValueError("BGE checkpoint requires PyTorch >=2.6 with weights-only loading")
            snapshot = snapshot_download(
                self.model_id, revision=self.revision, cache_dir=str(self.model_cache),
                token=False, local_files_only=self.offline,
                allow_patterns=["config.json", "model.safetensors", "tokenizer*.json",
                                "special_tokens_map.json", "sentencepiece.bpe.model", "modules.json",
                                "sentence_bert_config.json", "config_sentence_transformers.json",
                                "1_Pooling/config.json"] + ([] if self.safetensors else ["pytorch_model.bin"]),
            )
            self._model = SentenceTransformer(
                str(snapshot), device="cpu", local_files_only=True, trust_remote_code=False,
                model_kwargs={"use_safetensors": self.safetensors, "weights_only": True},
            )
            self._model.max_seq_length = 512
        return self._model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True,
                                  convert_to_numpy=True, show_progress_bar=False, prompt="")


class BGEEncoder(E5Encoder):
    """Pinned BGE-M3 dense embeddings; 512-token CPU comparison, no remote code."""
    model_id = "BAAI/bge-m3"
    revision = "5617a9f61b028005a4858fdac845db406aefb181"
    dimensions = 1024
    query_prefix, passage_prefix, batch_size = "", "", 4
    pooling = "model-defined CLS pooling"
    # Publisher's pinned checkpoint is PyTorch, loaded explicitly weights-only.
    safetensors = False


def make_encoder(name, cache, offline=False):
    if name not in {"e5-small", "bge-m3"}:
        raise ValueError("Choose embedding model e5-small or bge-m3")
    return (E5Encoder if name == "e5-small" else BGEEncoder)(cache, offline)


def _vectors(values, rows: int, dimensions: int, normalize: bool = True):
    matrix = np.asarray(values, dtype=np.float32)
    if matrix.shape != (rows, dimensions) or not np.isfinite(matrix).all():
        raise ValueError("Invalid embedding dimensions or non-finite values")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if (norms <= 0).any():
        raise ValueError("Zero-length embeddings are invalid")
    if normalize:
        return matrix / norms
    if not np.allclose(norms, 1, atol=1e-5):
        raise ValueError("Cached embeddings are not normalized")
    return matrix


class SemanticIndex:
    def __init__(self, documents: list[SearchDocument], encoder, cache_dir: Path,
                 rebuild: bool = False):
        self.documents = prepare_documents(documents)
        self.corpus_sha256 = corpus_fingerprint(self.documents)
        self.encoder = encoder
        self.encoder_config = encoder.configuration()
        self.dimensions = self.encoder_config["dimensions"]
        config = {"schema_version": 1, "corpus_sha256": self.corpus_sha256,
                  "encoder": self.encoder_config,
                  "evidence_ids": [doc.evidence_id for doc in self.documents]}
        key = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
        directory = cache_dir / key
        manifest_path = directory / "manifest.json"
        self.cache_hit = False
        if manifest_path.is_file() and not rebuild:
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                filename = manifest["matrix_file"]
                if manifest["config"] != config or Path(filename).name != filename or not filename.endswith(".npy"):
                    raise ValueError("Cache metadata mismatch")
                matrix_path = directory / filename
                if matrix_path.is_symlink() or hashlib.sha256(matrix_path.read_bytes()).hexdigest() != manifest["matrix_sha256"]:
                    raise ValueError("Cache checksum mismatch")
                self.matrix = _vectors(np.load(matrix_path, allow_pickle=False), len(self.documents),
                                       self.dimensions, normalize=False)
                self.cache_hit = True
            except (OSError, ValueError, KeyError, TypeError):
                raise ValueError("Embedding cache is invalid; rerun with --rebuild-embeddings") from None
        else:
            prefix = self.encoder_config["passage_prefix"]
            self.matrix = _vectors(encoder.encode([prefix + doc.text for doc in self.documents]),
                                   len(self.documents), self.dimensions)
            directory.mkdir(parents=True, exist_ok=True)
            filename = f"matrix-{uuid4().hex}.npy"
            matrix_path = directory / filename
            with matrix_path.open("xb") as handle:
                np.save(handle, self.matrix, allow_pickle=False)
            manifest = {"config": config, "matrix_file": filename,
                        "matrix_sha256": hashlib.sha256(matrix_path.read_bytes()).hexdigest()}
            temporary = directory / f"manifest-{uuid4().hex}.json"
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(manifest, handle, indent=2)
            temporary.replace(manifest_path)

    def configuration(self) -> dict:
        return {"algorithm": "semantic", "encoder": self.encoder_config,
                "document_count": len(self.documents), "corpus_sha256": self.corpus_sha256,
                "similarity": "cosine", "embedding_cache_hit": self.cache_hit}

    def search(self, query: str, top_k: int = 5) -> list[SearchHit]:
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            raise ValueError("top-k must be a positive integer")
        if not tokenize(query):
            return []
        prefix = self.encoder_config["query_prefix"]
        vector = _vectors(self.encoder.encode([prefix + query]), 1, self.dimensions)[0]
        scores = np.clip(self.matrix @ vector, -1, 1)
        order = sorted(range(len(self.documents)), key=lambda i: (-float(scores[i]), self.documents[i].evidence_id))
        return [SearchHit(self.documents[i], float(scores[i]), {}, score_kind="cosine") for i in order[:top_k]]

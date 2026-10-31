"""Optional local multilingual cross-encoder; scores only retrieved public candidates."""
import math
from pathlib import Path
from .retrieval import SearchHit

MODEL_ID = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
MODEL_REVISION = "1427fd652930e4ba29e8149678df786c240d8825"


class MiniLMScorer:
    def __init__(self, cache: Path, offline=False):
        self.cache, self.offline, self._model = cache, offline, None

    def configuration(self):
        return {"model": MODEL_ID, "revision": MODEL_REVISION, "device": "cpu",
                "max_length": 512, "batch_size": 8, "remote_code": False}

    def score(self, pairs):
        if self._model is None:
            import torch
            from huggingface_hub import snapshot_download
            from sentence_transformers import CrossEncoder
            torch.set_num_threads(4)
            snapshot = snapshot_download(MODEL_ID, revision=MODEL_REVISION, cache_dir=str(self.cache),
                token=False, local_files_only=self.offline,
                allow_patterns=['config.json', 'model.safetensors', 'sentencepiece.bpe.model',
                                'tokenizer*.json', 'special_tokens_map.json'])
            self._model = CrossEncoder(str(snapshot), device='cpu', max_length=512,
                                      trust_remote_code=False, model_kwargs={'use_safetensors': True})
        return self._model.predict(pairs, batch_size=8, show_progress_bar=False, convert_to_numpy=True)


class RerankedIndex:
    def __init__(self, index, scorer, candidate_k=20):
        if type(candidate_k) is not int or not 1 <= candidate_k <= 100:
            raise ValueError('Reranking candidate depth must be from 1 to 100')
        self.index, self.scorer, self.candidate_k = index, scorer, candidate_k
        self.documents = index.documents

    def configuration(self):
        base = self.index.configuration()
        return {**base, 'algorithm': 'reranked_' + base['algorithm'], 'retriever': base,
                'reranker': self.scorer.configuration(), 'rerank_candidate_k': self.candidate_k}

    def search(self, query, top_k=5):
        if type(top_k) is not int or not 1 <= top_k <= 100:
            raise ValueError('Reranking top-k must be from 1 to 100')
        candidates = self.index.search(query, max(top_k, self.candidate_k))
        if not candidates:
            return []
        scores = self.scorer.score([(query, hit.document.text) for hit in candidates])
        if len(scores) != len(candidates):
            raise ValueError('Reranker returned the wrong number of scores')
        ranked = []
        for rank, (hit, score) in enumerate(zip(candidates, scores), 1):
            score = float(score)
            if not math.isfinite(score):
                raise ValueError('Reranker returned a non-finite score')
            ranked.append(SearchHit(hit.document, score, hit.term_scores, 'cross_encoder',
                                    {**hit.components, 'pre_rerank_rank': rank, 'pre_rerank_score': hit.score}))
        return sorted(ranked, key=lambda h: (-h.score, h.document.evidence_id))[:top_k]

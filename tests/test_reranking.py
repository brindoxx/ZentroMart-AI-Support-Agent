"""Reranking invariants and model configuration with no downloads."""
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock
from zentromart.reranking import RerankedIndex
from zentromart.retrieval import SearchDocument, SearchHit
HAS_NUMPY = importlib.util.find_spec('numpy') is not None
if HAS_NUMPY:
    from zentromart.semantic import E5Encoder, BGEEncoder, make_encoder


class RerankingTests(unittest.TestCase):
    def index(self, scores):
        docs = [SearchDocument(x, x, 'public ' + x, 'kb/test', {'status':'current'}) for x in ('A','B')]
        base = MagicMock()
        base.documents = docs
        base.search.return_value = [SearchHit(d, 1, {}) for d in docs]
        base.configuration.return_value = {'algorithm':'hybrid', 'corpus_sha256':'test'}
        scorer = MagicMock()
        scorer.score.return_value = scores
        return RerankedIndex(base, scorer), base, scorer

    def test_only_public_retrieved_candidates_are_reordered_and_keep_provenance(self):
        index, base, scorer = self.index([0.1,0.9])
        hits = index.search('a question', 1)
        base.search.assert_called_once_with('a question',20)
        scorer.score.assert_called_once_with([('a question','public A'),('a question','public B')])
        self.assertEqual(hits[0].document.evidence_id,'B')
        self.assertEqual(hits[0].score_kind,'cross_encoder')
        self.assertEqual(hits[0].components['pre_rerank_rank'],2)

    def test_empty_candidates_do_not_load_scorer(self):
        index, base, scorer = self.index([])
        base.search.return_value=[]
        self.assertEqual(index.search('question'),[])
        scorer.score.assert_not_called()

    def test_invalid_scores_fail_instead_of_returning_fake_ranking(self):
        for scores in ([1], [float('nan'),1], [float('inf'),1]):
            index, _, _ = self.index(scores)
            with self.assertRaises(ValueError): index.search('question')

    @unittest.skipUnless(HAS_NUMPY, 'Install semantic dependencies')
    def test_encoder_configs_separate_caches_and_model_specific_prefixes(self):
        e5,bge=E5Encoder(Path('unused')),BGEEncoder(Path('unused'))
        self.assertEqual(e5.configuration()['dimensions'],384)
        self.assertEqual(bge.configuration()['dimensions'],1024)
        self.assertEqual(bge.configuration()['query_prefix'],'')
        self.assertNotEqual(e5.configuration()['revision'],bge.configuration()['revision'])
        self.assertEqual(len(bge.revision),40)
        with self.assertRaises(ValueError):make_encoder('arbitrary-repository',Path('unused'))

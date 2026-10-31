"""Bounded local E5/BGE and reranking comparison; no Gemini or speech calls."""
import argparse
import gc
import json
from time import perf_counter
from .retrieval import evaluate_retrieval
from .runner import save_report
from ..config import load_settings
from ..retrieval import build_indexes, load_search_documents


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', nargs='+', choices=['e5-small', 'bge-m3'], default=['e5-small', 'bge-m3'])
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--rerank', action='store_true')
    parser.add_argument('--rerank-only', action='store_true', help='Skip repeated base metrics; evaluate reranked top-5 only')
    parser.add_argument('--variants', choices=['question','asr_text','both'], default='both')
    args = parser.parse_args()
    args.rerank = args.rerank or args.rerank_only
    variants = (False, True) if args.variants == 'both' else (args.variants == 'asr_text',)
    settings = load_settings()
    documents = load_search_documents(settings.dataset_dir)
    runs, failures = [], []
    for name in args.models:
        index = indexes = None
        try:
            started = perf_counter()
            print('Preparing ' + name, flush=True)
            indexes = build_indexes(documents, settings.artifacts_dir, ('hybrid',), offline=args.offline,
                                    embedding_model=name, reranker='none')
            index = indexes['hybrid']
            index.search('support', 20)  # Warm-up; not a practice/gold query.
            setup = round(perf_counter() - started, 3)
            # Independent exact cosine formulation, not a claim of testing FAISS.
            import numpy as np
            from scipy.spatial.distance import cdist
            semantic = index.semantic
            vector = semantic.encoder.encode([semantic.encoder_config['query_prefix'] + 'refund'])[0]
            vector = vector / np.linalg.norm(vector)
            parity = bool(np.allclose(semantic.matrix @ vector,
                                     1 - cdist(semantic.matrix, vector[None, :], metric='cosine')[:, 0], atol=1e-5))
            for asr in (() if args.rerank_only else variants):
                for depth in (5, 20):
                    report = evaluate_retrieval(settings, index, top_k=depth, asr=asr)
                    path = save_report(report, settings.artifacts_dir)
                    runs.append({'embedding': name, 'reranked': False, 'top_k': depth,
                                 'input_variant': report['input_variant'], 'index': report['index'],
                                 'summary': report['summary'], 'by_language': report['by_language'],
                                 'setup_seconds': setup, 'exact_cosine_parity': parity, 'report': str(path)})
                    print(json.dumps({key:runs[-1][key] for key in ('embedding','reranked','top_k','input_variant','summary')}), flush=True)
            if args.rerank:
                print('Reranking candidates for ' + name, flush=True)
                from ..reranking import MiniLMScorer, RerankedIndex
                reranked = RerankedIndex(index, MiniLMScorer(settings.artifacts_dir / 'models', args.offline))
                reranked.search('support', 5)
                for asr in variants:
                    report = evaluate_retrieval(settings, reranked, top_k=5, asr=asr)
                    path = save_report(report, settings.artifacts_dir)
                    runs.append({'embedding': name, 'reranked': True, 'top_k': 5,
                                 'input_variant': report['input_variant'], 'index': report['index'],
                                 'summary': report['summary'], 'by_language': report['by_language'], 'report': str(path)})
                    print(json.dumps({key:runs[-1][key] for key in ('embedding','reranked','top_k','input_variant','summary')}), flush=True)
                del reranked
        except Exception as error:
            failures.append({'embedding': name, 'error_type': type(error).__name__})
            print(name + ': incomplete experiment (' + type(error).__name__ + ')', flush=True)
        finally:
            del index, indexes
            gc.collect()
    result = {'schema_version': 1, 'run_kind': 'local_retrieval_experiment', 'runs': runs,
              'failures': failures, 'practice_only': True, 'cloud_calls': 0,
              'limitations': ['Development set, not a held-out benchmark.',
                  'Warm search latency excludes model download and warm-up.',
                  'Exact cosine parity compares NumPy with SciPy, not a FAISS benchmark.',
                  'Retrieval scores do not measure generated answer quality or policy applicability.']}
    print('Experiment report: ' + str(save_report(result, settings.artifacts_dir)), flush=True)


if __name__ == '__main__':
    main()

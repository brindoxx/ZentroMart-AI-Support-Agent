"""Public retrieval resources; conversation state and credentials are never cached here."""
from pathlib import Path
from threading import RLock
from .retrieval import build_indexes, load_search_documents


class SharedIndex:
    """Serialize CPU encoder access; retain no queries, replies or private records."""
    def __init__(self, index):
        self._index = index
        self.documents = index.documents
        self._lock = RLock()

    def search(self, query, top_k=5):
        with self._lock:
            return self._index.search(query, top_k)

    def configuration(self):
        return self._index.configuration()


def build_public_index(dataset_dir, artifacts_dir, method="hybrid", offline=False):
    documents = load_search_documents(Path(dataset_dir))
    return SharedIndex(build_indexes(documents, Path(artifacts_dir), (method,), offline=offline)[method])

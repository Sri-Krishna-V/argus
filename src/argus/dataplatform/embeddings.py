"""Embedding provider. Default is fastembed (ONNX all-MiniLM-L6-v2): local,
deterministic, no CUDA-sized torch download. Model name + version are stamped on
every chunk row, so a provider swap is a config change plus `argus reprocess`."""

import hashlib
import math

from argus.core.config import get_settings
from argus.knowledge.models import EMBEDDING_DIM

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class FastEmbedProvider:
    name = f"fastembed/{MODEL_NAME}"

    def __init__(self) -> None:
        from fastembed import TextEmbedding  # lazy: model download on first use

        self._model = TextEmbedding(MODEL_NAME)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts)]


class FakeProvider:
    """Deterministic bag-of-words feature hashing for tests: no model download, and
    texts sharing vocabulary get genuinely similar vectors, so hybrid-retrieval tests
    exercise the semantic signal instead of fighting hash noise."""

    name = "fake/feature-hash-bow"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * EMBEDDING_DIM
            for token in text.lower().split():
                digest = hashlib.sha256(token.encode()).digest()
                dim = int.from_bytes(digest[:4]) % EMBEDDING_DIM
                sign = 1.0 if digest[4] % 2 else -1.0
                vec[dim] += sign
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / norm for x in vec])
        return out


_provider = None


def get_provider():
    global _provider
    if _provider is None:
        kind = get_settings().embedding_provider
        _provider = FakeProvider() if kind == "fake" else FastEmbedProvider()
    return _provider

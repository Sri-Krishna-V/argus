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
    """Deterministic hash-based vectors for tests; no model download."""

    name = "fake/deterministic-sha256"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            seed = hashlib.sha256(text.encode()).digest()
            raw = [seed[i % len(seed)] - 128 for i in range(EMBEDDING_DIM)]
            norm = math.sqrt(sum(x * x for x in raw)) or 1.0
            out.append([x / norm for x in raw])
        return out


_provider = None


def get_provider():
    global _provider
    if _provider is None:
        kind = get_settings().embedding_provider
        _provider = FakeProvider() if kind == "fake" else FastEmbedProvider()
    return _provider

"""Embeddings with OpenAI when available and deterministic local fallback."""

from __future__ import annotations

from typing import Iterable, List
import hashlib
import math
import re

import numpy as np
import openai

from config import Config


class EmbeddingService:
    def __init__(self) -> None:
        self.dimension = Config.HASH_EMBEDDING_DIM
        self.model_name = Config.OPENAI_EMBEDDING_MODEL
        self.use_mock = Config.use_mock_mode()
        if Config.OPENAI_API_KEY:
            openai.api_key = Config.OPENAI_API_KEY

    def embed_text(self, text: str) -> List[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: Iterable[str]) -> List[List[float]]:
        texts = list(texts)
        if not texts:
            return []

        if not self.use_mock:
            try:
                response = openai.Embedding.create(
                    model=self.model_name,
                    input=texts,
                )
                return [item["embedding"] for item in response["data"]]
            except Exception:
                self.use_mock = True

        return [self._hash_embedding(text) for text in texts]

    def _hash_embedding(self, text: str) -> List[float]:
        vector = np.zeros(self.dimension, dtype=float)
        tokens = re.findall(r"[A-Za-z0-9_]+", text.lower())
        if not tokens:
            return vector.tolist()

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            weight = 1.0 / max(1.0, math.log(len(token) + 1))
            vector[idx] += sign * weight

        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        return vector.tolist()


embedding_service = EmbeddingService()

"""
retriever.py
单论文向量检索，集成 embedding 缓存。
"""

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

from src.cache import load_cache, save_cache
from src.config import get_embedding_model


class PaperRetriever:
    def __init__(
        self,
        chunks: list[dict],
        model_name: str | None = None,
        pdf_path: str | None = None,
    ):
        """
        Args:
            chunks: chunker.chunk_pages 的返回值
            model_name: sentence-transformers 模型（None 则用 config 默认，支持中文）
            pdf_path: 原始 PDF 路径，用于命中/写入缓存（None 则不缓存）
        """
        self.chunks = chunks
        self.model_name = model_name or get_embedding_model()
        self.model = SentenceTransformer(self.model_name)

        embeddings = self._get_embeddings(chunks, pdf_path)

        dim = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dim)
        self.index.add(np.array(embeddings, dtype="float32"))

    def _get_embeddings(
        self, chunks: list[dict], pdf_path: str | None
    ) -> np.ndarray:
        # 尝试命中缓存（按 PDF + 模型）
        if pdf_path:
            cached = load_cache(pdf_path, self.model_name)
            if cached is not None:
                cached_chunks, embeddings = cached
                if len(cached_chunks) == len(chunks):
                    return embeddings
                print("[Cache] chunk 数量不一致，重新 embedding...")

        # 计算 embedding
        print(f"[Retriever] 正在 embedding {len(chunks)} 个 chunk（{self.model_name}）...")
        texts = [c["text"] for c in chunks]
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=True,
            batch_size=32,
        )
        embeddings = np.array(embeddings, dtype="float32")

        # 写入缓存
        if pdf_path:
            save_cache(pdf_path, chunks, embeddings, self.model_name)

        return embeddings

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        q = self.model.encode([query], normalize_embeddings=True)
        scores, ids = self.index.search(np.array(q, dtype="float32"), top_k)
        results = []
        for score, idx in zip(scores[0], ids[0]):
            if idx < 0:
                continue
            c = self.chunks[idx]
            results.append({"score": float(score), "page": c["page"], "text": c["text"]})
        return results

    def keyword_search(self, keyword: str, top_k: int = 5) -> list[dict]:
        kw = keyword.lower()
        matched = [c for c in self.chunks if kw in c["text"].lower()]
        matched.sort(key=lambda c: c["text"].lower().count(kw), reverse=True)
        return [{"score": 1.0, "page": c["page"], "text": c["text"]} for c in matched[:top_k]]

    def hybrid_search(self, query: str, top_k: int = 5) -> list[dict]:
        semantic = self.search(query, top_k=top_k)
        keyword = self.keyword_search(query, top_k=3)
        seen = set()
        merged = []
        for r in semantic + keyword:
            key = (r["page"], r["text"][:80])
            if key not in seen:
                seen.add(key)
                merged.append(r)
        return merged[:top_k + 2]

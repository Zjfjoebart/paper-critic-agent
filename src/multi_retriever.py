"""
multi_retriever.py
多论文检索器，集成 embedding 缓存。
每篇论文独立缓存，新增一篇不影响其他论文的缓存。
"""

import numpy as np
import faiss
from pathlib import Path
from sentence_transformers import SentenceTransformer

from src.parse_pdf import parse_pdf
from src.chunker import chunk_pages
from src.cache import load_cache, save_cache
from src.config import get_embedding_model


class MultiPaperRetriever:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or get_embedding_model()
        self.model = SentenceTransformer(self.model_name)
        self.dim = self.model.get_sentence_embedding_dimension()
        self.index = faiss.IndexFlatIP(self.dim)

        self.chunks: list[dict] = []   # 与 FAISS 索引行一一对应
        self.papers: dict[int, dict] = {}
        self._next_paper_id = 0

    # ------------------------------------------------------------------ #
    #  加载论文（带缓存）
    # ------------------------------------------------------------------ #

    def add_paper(self, pdf_path: str, alias: str | None = None) -> int:
        path = Path(pdf_path)
        name = alias or path.stem
        paper_id = self._next_paper_id
        self._next_paper_id += 1

        print(f"\n[MultiRetriever] [{paper_id}] {name}")

        # 尝试命中缓存
        cached = load_cache(str(path), self.model_name)
        if cached is not None:
            base_chunks, embeddings = cached
        else:
            # 解析 + 切块 + embedding
            pages = parse_pdf(str(path))
            base_chunks = chunk_pages(pages)
            print(f"  → {len(base_chunks)} 块，正在 embedding...")
            texts = [c["text"] for c in base_chunks]
            embeddings = self.model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False,
                batch_size=32,
            )
            embeddings = np.array(embeddings, dtype="float32")
            save_cache(str(path), base_chunks, embeddings, self.model_name)

        # 注入 paper 信息
        tagged_chunks = [
            {**c, "paper_id": paper_id, "paper_name": name}
            for c in base_chunks
        ]

        self.index.add(embeddings)
        self.chunks.extend(tagged_chunks)

        page_count = base_chunks[-1]["page"] if base_chunks else 0
        self.papers[paper_id] = {
            "paper_id": paper_id,
            "name": name,
            "path": str(path),
            "chunk_count": len(tagged_chunks),
            "page_count": page_count,
        }
        print(f"  → 就绪，{page_count} 页，{len(tagged_chunks)} 块")
        return paper_id

    # ------------------------------------------------------------------ #
    #  检索
    # ------------------------------------------------------------------ #

    def search(self, query: str, top_k: int = 5, paper_id: int | None = None) -> list[dict]:
        q = self.model.encode([query], normalize_embeddings=True)
        k = top_k * 3 if paper_id is not None else top_k
        scores, ids = self.index.search(np.array(q, dtype="float32"), k)

        results = []
        for score, idx in zip(scores[0], ids[0]):
            if idx < 0:
                continue
            c = self.chunks[idx]
            if paper_id is not None and c["paper_id"] != paper_id:
                continue
            results.append({
                "score": float(score),
                "paper_id": c["paper_id"],
                "paper_name": c["paper_name"],
                "page": c["page"],
                "text": c["text"],
            })
            if len(results) >= top_k:
                break
        return results

    def keyword_search(self, keyword: str, top_k: int = 5, paper_id: int | None = None) -> list[dict]:
        kw = keyword.lower()
        pool = self.chunks if paper_id is None else [c for c in self.chunks if c["paper_id"] == paper_id]
        matched = [c for c in pool if kw in c["text"].lower()]
        matched.sort(key=lambda c: c["text"].lower().count(kw), reverse=True)
        return [
            {"score": 1.0, "paper_id": c["paper_id"], "paper_name": c["paper_name"],
             "page": c["page"], "text": c["text"]}
            for c in matched[:top_k]
        ]

    def hybrid_search(self, query: str, top_k: int = 5, paper_id: int | None = None) -> list[dict]:
        semantic = self.search(query, top_k=top_k, paper_id=paper_id)
        keyword = self.keyword_search(query, top_k=3, paper_id=paper_id)
        seen = set()
        merged = []
        for r in semantic + keyword:
            key = (r["paper_id"], r["page"], r["text"][:80])
            if key not in seen:
                seen.add(key)
                merged.append(r)
        return merged[:top_k + 2]

    def search_per_paper(self, query: str, top_k_per_paper: int = 3) -> dict[int, list[dict]]:
        return {
            pid: self.hybrid_search(query, top_k=top_k_per_paper, paper_id=pid)
            for pid in self.papers
        }

    # ------------------------------------------------------------------ #
    #  工具方法
    # ------------------------------------------------------------------ #

    def paper_list_str(self) -> str:
        lines = [f"当前共加载 {len(self.papers)} 篇论文："]
        for pid, info in self.papers.items():
            lines.append(
                f"  [{pid}] {info['name']}（{info['page_count']} 页，{info['chunk_count']} 块）"
            )
        return "\n".join(lines)

    def format_results(self, results: list[dict]) -> str:
        if not results:
            return "未找到相关内容。"
        parts = [
            f"[论文：{r['paper_name']} | p.{r['page']} | 相关度={r['score']:.3f}]\n{r['text']}"
            for r in results
        ]
        return "\n\n---\n\n".join(parts)

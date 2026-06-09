"""
library.py
本地论文库索引（v0.4）。

把"一次读几篇"升级为"管理整个文献库"：
- 扫描 papers/ 目录下所有 PDF
- 持久化整库 FAISS 索引到 data/index/，元数据到 data/index/library.json
- 增量更新：只对新增/改动的 PDF 做 embedding，已索引的跳过
- 启动时直接加载已有索引，无需重复 embedding
- 对外暴露与 MultiPaperRetriever 相同的检索接口，可直接接入 build_multi_agent

判断"是否已索引"用每个 PDF 的内容哈希 + 当前 embedding 模型；
换论文内容或换模型都会触发重新 embedding。
"""

import json
from pathlib import Path

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

from src.parse_pdf import parse_pdf
from src.chunker import chunk_pages
from src.cache import _pdf_hash
from src.config import get_embedding_model


INDEX_DIR = Path("data/index")
FAISS_FILE = INDEX_DIR / "library.faiss"
META_FILE = INDEX_DIR / "library.json"


class LibraryRetriever:
    """
    持久化的多论文库检索器。
    检索接口（search / keyword_search / hybrid_search / search_per_paper /
    paper_list_str / format_results）与 MultiPaperRetriever 保持一致。
    """

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or get_embedding_model()
        self.model = SentenceTransformer(self.model_name)
        self.dim = self.model.get_sentence_embedding_dimension()
        self.index = faiss.IndexFlatIP(self.dim)

        self.chunks: list[dict] = []        # 与 FAISS 行一一对应
        self.embeddings: np.ndarray = np.zeros((0, self.dim), dtype="float32")
        self.papers: dict[int, dict] = {}   # paper_id -> info
        self._next_paper_id = 0

    # ------------------------------------------------------------------ #
    #  持久化
    # ------------------------------------------------------------------ #

    def save(self) -> None:
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(FAISS_FILE))
        meta = {
            "model_name": self.model_name,
            "dim": self.dim,
            "next_paper_id": self._next_paper_id,
            "papers": list(self.papers.values()),
            "chunks": self.chunks,
        }
        META_FILE.write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )
        print(f"[Library] 索引已保存：{len(self.papers)} 篇 / {len(self.chunks)} 块 → {INDEX_DIR}")

    def load(self) -> bool:
        """加载已有索引。返回 True 表示加载成功且可用。"""
        if not (FAISS_FILE.exists() and META_FILE.exists()):
            return False
        try:
            meta = json.loads(META_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[Library] 元数据损坏，将重建：{e}")
            return False

        # 模型不一致则不能复用（向量维度/语义都不同）
        if meta.get("model_name") != self.model_name:
            print(f"[Library] 索引模型({meta.get('model_name')}) 与当前({self.model_name})不一致，将重建。")
            return False

        self.index = faiss.read_index(str(FAISS_FILE))
        self.chunks = meta["chunks"]
        self.papers = {p["paper_id"]: p for p in meta["papers"]}
        self._next_paper_id = meta["next_paper_id"]
        self.embeddings = self.index.reconstruct_n(0, self.index.ntotal) if self.index.ntotal else \
            np.zeros((0, self.dim), dtype="float32")
        print(f"[Library] 已加载索引：{len(self.papers)} 篇 / {len(self.chunks)} 块")
        return True

    # ------------------------------------------------------------------ #
    #  构建 / 增量更新
    # ------------------------------------------------------------------ #

    def _indexed_hashes(self) -> set[str]:
        return {p["hash"] for p in self.papers.values()}

    def _indexed_paths(self) -> set[str]:
        return {p["path"] for p in self.papers.values()}

    def sync(self, papers_dir: str) -> dict:
        """
        将 papers_dir 与索引同步：
        - 新增/改动的 PDF → 解析、embedding、加入索引
        - 已索引且未变的 PDF → 跳过
        返回统计 {added, skipped, total}。
        """
        d = Path(papers_dir)
        d.mkdir(parents=True, exist_ok=True)
        pdfs = sorted(d.glob("*.pdf"))

        indexed = self._indexed_hashes()
        added, skipped = 0, 0

        for pdf in pdfs:
            h = _pdf_hash(str(pdf))
            if h in indexed:
                skipped += 1
                continue
            self._add_paper(str(pdf), h)
            indexed.add(h)
            added += 1

        if added:
            self.save()
        stats = {"added": added, "skipped": skipped, "total": len(pdfs)}
        print(f"[Library] 同步完成：新增 {added}，跳过 {skipped}，共 {len(pdfs)} 个 PDF")
        return stats

    def _add_paper(self, pdf_path: str, file_hash: str) -> int:
        path = Path(pdf_path)
        name = path.stem
        paper_id = self._next_paper_id
        self._next_paper_id += 1

        print(f"\n[Library] 索引 [{paper_id}] {name}")
        pages = parse_pdf(str(path))
        base_chunks = chunk_pages(pages)
        print(f"  → {len(base_chunks)} 块，embedding（{self.model_name}）...")
        texts = [c["text"] for c in base_chunks]
        embs = self.model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False, batch_size=32
        )
        embs = np.array(embs, dtype="float32")

        tagged = [
            {**c, "paper_id": paper_id, "paper_name": name}
            for c in base_chunks
        ]
        self.index.add(embs)
        self.chunks.extend(tagged)
        self.embeddings = np.vstack([self.embeddings, embs]) if self.embeddings.size else embs

        page_count = base_chunks[-1]["page"] if base_chunks else 0
        self.papers[paper_id] = {
            "paper_id": paper_id,
            "name": name,
            "path": str(path),
            "hash": file_hash,
            "chunk_count": len(tagged),
            "page_count": page_count,
        }
        print(f"  → 就绪，{page_count} 页，{len(tagged)} 块")
        return paper_id

    # ------------------------------------------------------------------ #
    #  检索（接口对齐 MultiPaperRetriever）
    # ------------------------------------------------------------------ #

    def search(self, query: str, top_k: int = 5, paper_id: int | None = None) -> list[dict]:
        if self.index.ntotal == 0:
            return []
        q = self.model.encode([query], normalize_embeddings=True)
        k = top_k * 3 if paper_id is not None else top_k
        k = min(k, self.index.ntotal)
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
        lines = [f"论文库当前共 {len(self.papers)} 篇论文："]
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


def build_or_load_library(papers_dir: str = "papers", rebuild: bool = False) -> LibraryRetriever:
    """
    入口函数：加载已有索引并与 papers_dir 增量同步；rebuild=True 则忽略旧索引重建。
    """
    lib = LibraryRetriever()
    if not rebuild:
        lib.load()
    lib.sync(papers_dir)
    return lib

"""
cache.py
PDF embedding 缓存。

策略：
- cache key = PDF 文件 SHA256 前 16 位 + embedding 模型标签
  （含模型名，避免切换模型后复用旧向量这种脏缓存）
- 缓存内容：chunks（文本 + 页码）+ numpy embeddings
- 格式：gzip + pickle（单文件，含压缩）
- 存储路径：data/cache/<stem>_<hash16>_<model>.pkl.gz

命中缓存时完全跳过 embedding 计算（节省 10~60 秒）。
"""

import hashlib
import pickle
import gzip
from pathlib import Path
from typing import Optional
import numpy as np

from src.config import get_embedding_model, model_tag


CACHE_DIR = Path("data/cache")


def _pdf_hash(pdf_path: str) -> str:
    """计算 PDF 文件的 SHA256，返回前 16 位十六进制字符串。"""
    h = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()[:16]


def _cache_path(pdf_path: str, model_name: Optional[str] = None) -> Path:
    stem = Path(pdf_path).stem
    key = _pdf_hash(pdf_path)
    tag = model_tag(model_name or get_embedding_model())
    return CACHE_DIR / f"{stem}_{key}_{tag}.pkl.gz"


def load_cache(
    pdf_path: str, model_name: Optional[str] = None
) -> Optional[tuple[list[dict], np.ndarray]]:
    """
    尝试加载缓存。

    Returns:
        (chunks, embeddings) 或 None（缓存未命中）
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(pdf_path, model_name)

    if not path.exists():
        return None

    try:
        with gzip.open(path, "rb") as f:
            data = pickle.load(f)
        chunks: list[dict] = data["chunks"]
        embeddings: np.ndarray = data["embeddings"]
        print(f"[Cache] 命中缓存：{path.name}（{len(chunks)} 块，跳过 embedding）")
        return chunks, embeddings
    except Exception as e:
        print(f"[Cache] 缓存损坏，重新计算：{e}")
        path.unlink(missing_ok=True)
        return None


def save_cache(
    pdf_path: str,
    chunks: list[dict],
    embeddings: np.ndarray,
    model_name: Optional[str] = None,
) -> None:
    """将 chunks + embeddings 写入缓存文件。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(pdf_path, model_name)

    data = {
        "chunks": chunks,
        "embeddings": embeddings,
        "model": model_name or get_embedding_model(),
    }
    with gzip.open(path, "wb", compresslevel=3) as f:
        pickle.dump(data, f)

    size_kb = path.stat().st_size / 1024
    print(f"[Cache] 已保存：{path.name}（{size_kb:.0f} KB）")


def list_cache() -> list[dict]:
    """列出所有缓存文件及其大小。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    result = []
    for p in sorted(CACHE_DIR.glob("*.pkl.gz")):
        result.append({
            "name": p.name,
            "size_kb": p.stat().st_size / 1024,
            "path": str(p),
        })
    return result


def clear_cache(pdf_path: Optional[str] = None) -> int:
    """
    清除缓存。
    pdf_path 为 None 时清除全部；否则清除该 PDF 在所有模型下的缓存。
    返回删除的文件数量。
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if pdf_path is not None:
        stem = Path(pdf_path).stem
        key = _pdf_hash(pdf_path)
        count = 0
        for p in CACHE_DIR.glob(f"{stem}_{key}_*.pkl.gz"):
            p.unlink()
            count += 1
        return count

    count = 0
    for p in CACHE_DIR.glob("*.pkl.gz"):
        p.unlink()
        count += 1
    return count

"""
config.py
集中管理可配置项，主要是 embedding 模型选择。

环境变量：
  EMBEDDING_MODEL   sentence-transformers 模型名，默认多语言模型（支持中文）。

说明：
- 默认 `paraphrase-multilingual-MiniLM-L12-v2`，384 维，中英文都可用。
- 若只读英文论文、想要更快更小的模型，可设 EMBEDDING_MODEL=all-MiniLM-L6-v2。
- 切换模型后，旧 embedding 缓存会因 cache key 含模型名而自动失效、重新计算，
  不会出现"用 A 模型的向量配 B 模型的查询"这种脏数据。
"""

import os

# 默认多语言模型：兼顾中英文论文
DEFAULT_EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


def get_embedding_model() -> str:
    """返回当前使用的 embedding 模型名（环境变量优先）。"""
    return os.environ.get("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip()


def model_tag(model_name: str) -> str:
    """把模型名压成一个适合放进文件名的短标签。"""
    # 取模型名最后一段，去掉非字母数字
    base = model_name.split("/")[-1]
    return "".join(ch for ch in base if ch.isalnum() or ch in "-_")[:32]

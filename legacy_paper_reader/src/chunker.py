"""
chunker.py
将解析后的页面文本切分为适合检索的 chunk。
策略：滑动窗口 + 保留页码信息，让每个 chunk 可追溯原始位置。
"""


def chunk_pages(
    pages: list[dict],
    chunk_size: int = 1200,
    overlap: int = 200,
) -> list[dict]:
    """
    对所有页面文本做滑动窗口切分。

    Args:
        pages: parse_pdf 的返回值
        chunk_size: 每个 chunk 的最大字符数
        overlap: 相邻 chunk 的重叠字符数（保留上下文）

    Returns:
        [{"chunk_id": int, "page": int, "text": str}, ...]
    """
    chunks = []
    chunk_id = 0

    for page in pages:
        # 清理多余空白
        text = " ".join(page["text"].split())

        if len(text) <= chunk_size:
            # 页面本身就很短，直接作为一个 chunk
            chunks.append({
                "chunk_id": chunk_id,
                "page": page["page"],
                "text": text,
            })
            chunk_id += 1
            continue

        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk_text = text[start:end]

            # 尽量在句子边界断开（仅当后面还有内容时）
            if end < len(text):
                last_period = max(
                    chunk_text.rfind(". "),
                    chunk_text.rfind(".\n"),
                    chunk_text.rfind("? "),
                    chunk_text.rfind("! "),
                )
                if last_period > chunk_size // 2:
                    chunk_text = chunk_text[:last_period + 1]

            chunks.append({
                "chunk_id": chunk_id,
                "page": page["page"],
                "text": chunk_text.strip(),
            })
            chunk_id += 1

            # 已经覆盖到页尾，结束本页
            if end >= len(text):
                break

            # 前进，保证至少推进 1 个字符，避免末尾窗口 <= overlap 时死循环
            advance = len(chunk_text) - overlap
            start += advance if advance > 0 else (len(chunk_text) or 1)

    return chunks

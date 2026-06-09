"""
parse_pdf.py
将 PDF 文件按页解析为文本，同时提取页面元数据。

对扫描版 PDF（无文字层）提供 OCR 兜底：
- 自动检测某页文字层是否近乎为空
- 若是，尝试用 PyMuPDF 内置 OCR（需系统安装 Tesseract）
- 若 Tesseract 不可用，打印清晰提示并跳过，不会崩溃
"""

import fitz  # PyMuPDF

# 单页文字少于该字符数，视为"可能是扫描页"，触发 OCR 兜底
_OCR_TRIGGER_CHARS = 20
_ocr_warned = False


def _ocr_page(page) -> str:
    """对单页做 OCR，失败（如未装 Tesseract）返回空串并只警告一次。"""
    global _ocr_warned
    try:
        tp = page.get_textpage_ocr(flags=0, full=True)
        return page.get_text("text", textpage=tp)
    except Exception as e:
        if not _ocr_warned:
            print(f"[parse_pdf] 检测到疑似扫描页，但 OCR 不可用（{e}）。"
                  f"如需识别扫描版 PDF，请安装 Tesseract OCR 后重试。")
            _ocr_warned = True
        return ""


def parse_pdf(pdf_path: str, ocr: bool = True) -> list[dict]:
    """
    解析 PDF，返回每页的文本内容。

    Args:
        pdf_path: PDF 路径
        ocr: 是否对无文字层的页面尝试 OCR 兜底（默认开）

    Returns:
        [{"page": int, "text": str}, ...]
    """
    doc = fitz.open(pdf_path)
    pages = []

    for i, page in enumerate(doc):
        text = page.get_text("text")
        # 文字层近乎为空 → 可能是扫描页，尝试 OCR
        if ocr and len(text.strip()) < _OCR_TRIGGER_CHARS:
            ocr_text = _ocr_page(page)
            if ocr_text.strip():
                text = ocr_text

        # 去掉过短的页（封面、页码页、OCR 失败页等）
        if len(text.strip()) < 50:
            continue
        pages.append({
            "page": i + 1,
            "text": text,
        })

    doc.close()
    return pages


def get_pdf_metadata(pdf_path: str) -> dict:
    """提取 PDF 元数据（标题、作者、页数等）。"""
    doc = fitz.open(pdf_path)
    meta = doc.metadata or {}
    total_pages = doc.page_count  # 必须在 close() 之前读取
    doc.close()
    return {
        "title": meta.get("title", "") or "Unknown",
        "author": meta.get("author", "") or "Unknown",
        "subject": meta.get("subject", ""),
        "total_pages": total_pages,
    }

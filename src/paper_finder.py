"""
paper_finder.py
联网搜索相关论文（Semantic Scholar Graph API，免费、无需 key）。

能拿到：标题 / 作者 / 年份 / 发表会议或期刊 / 引用数 / 摘要 / 开放获取 PDF 链接。
适合"找某主题的相关顶会论文"。

只依赖 Python 标准库（urllib + json）。
API 文档：https://api.semanticscholar.org/api-docs/graph
"""

import json
import time
import urllib.parse
import urllib.request

SEARCH_API = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,year,venue,citationCount,authors,abstract,externalIds,openAccessPdf,url"
_UA = {"User-Agent": "paper-critic-agent/0.6 (research use)"}

# 常见顶会/顶刊的识别关键词（小写匹配 venue 字符串）
TOP_VENUES = {
    # ML / AI
    "neurips", "nips", "icml", "iclr", "aaai", "ijcai",
    # CV
    "cvpr", "iccv", "eccv", "wacv",
    # NLP
    "acl", "emnlp", "naacl", "coling", "eacl",
    # 数据 / 检索 / 系统
    "kdd", "sigir", "www", "wsdm", "vldb", "sigmod", "osdi", "sosp", "mlsys",
    # 期刊
    "tpami", "jmlr", "nature", "science",
}


def _is_top_venue(venue: str) -> bool:
    v = (venue or "").lower()
    return any(tag in v for tag in TOP_VENUES)


def find_papers(
    query: str,
    limit: int = 20,
    top_only: bool = False,
    min_year: int | None = None,
) -> list[dict]:
    """
    搜索相关论文。

    Args:
        query: 主题关键词
        limit: 返回上限
        top_only: 只保留顶会/顶刊
        min_year: 只保留该年份及以后

    Returns:
        [{title, authors, year, venue, citations, is_top, abstract, pdf_url, url, arxiv_id}, ...]
        按引用数降序。
    """
    params = urllib.parse.urlencode({
        "query": query,
        "limit": min(max(limit * 2, limit), 100),  # 多取些，过滤后再截断
        "fields": FIELDS,
    })
    req = urllib.request.Request(f"{SEARCH_API}?{params}", headers=_UA)

    data = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:  # 限流，退避重试
                time.sleep(2 + attempt * 2)
                continue
            raise

    items = (data or {}).get("data", []) or []
    results = []
    for it in items:
        venue = it.get("venue") or ""
        year = it.get("year")
        if top_only and not _is_top_venue(venue):
            continue
        if min_year and (year or 0) < min_year:
            continue
        ext = it.get("externalIds") or {}
        oa = it.get("openAccessPdf") or {}
        results.append({
            "title": it.get("title", "").strip(),
            "authors": [a.get("name", "") for a in (it.get("authors") or [])],
            "year": year,
            "venue": venue,
            "citations": it.get("citationCount", 0),
            "is_top": _is_top_venue(venue),
            "abstract": (it.get("abstract") or "").strip(),
            "pdf_url": oa.get("url", "") or "",
            "url": it.get("url", "") or "",
            "arxiv_id": ext.get("ArXiv", "") or "",
        })

    results.sort(key=lambda r: (r["citations"] or 0), reverse=True)
    return results[:limit]


def format_results(results: list[dict]) -> str:
    """把搜索结果格式化成可读文本（用于 Agent 工具返回 / CLI 打印）。"""
    if not results:
        return "未找到相关论文。"
    lines = []
    for i, r in enumerate(results, 1):
        authors = ", ".join(r["authors"][:3]) + ("等" if len(r["authors"]) > 3 else "")
        star = " ⭐顶会" if r["is_top"] else ""
        venue = r["venue"] or "—"
        lines.append(
            f"[{i}] {r['title']}（{r['year']}）{star}\n"
            f"    {authors} | {venue} | 引用 {r['citations']}"
            + (f" | arXiv:{r['arxiv_id']}" if r["arxiv_id"] else "")
        )
    return "\n".join(lines)

"""
arxiv_search.py
arXiv 检索与下载，用来快速把相关论文喂进 papers/ 论文库。

只依赖 Python 标准库（urllib + xml），无需额外安装。
arXiv 官方 API：http://export.arxiv.org/api/query

用法（命令行）：
    python -m src.arxiv_search "token pruning vision language model"
    python -m src.arxiv_search "long context attention" --max 5 --download all
    python -m src.arxiv_search "kv cache compression" --download 1,3,4
"""

import sys
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

API = "http://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom"}
_UA = {"User-Agent": "paper-critic-agent/0.4 (research use)"}


def search_arxiv(query: str, max_results: int = 10) -> list[dict]:
    """
    检索 arXiv，返回论文列表。
    每项：{arxiv_id, title, authors, summary, pdf_url, published}
    """
    params = urllib.parse.urlencode({
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    })
    req = urllib.request.Request(f"{API}?{params}", headers=_UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")

    root = ET.fromstring(raw)
    results = []
    for entry in root.findall("atom:entry", NS):
        arxiv_url = entry.findtext("atom:id", default="", namespaces=NS)
        arxiv_id = arxiv_url.rsplit("/", 1)[-1]
        title = " ".join(entry.findtext("atom:title", "", NS).split())
        summary = " ".join(entry.findtext("atom:summary", "", NS).split())
        published = entry.findtext("atom:published", "", NS)[:10]
        authors = [
            a.findtext("atom:name", "", NS)
            for a in entry.findall("atom:author", NS)
        ]
        pdf_url = ""
        for link in entry.findall("atom:link", NS):
            if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                pdf_url = link.get("href", "")
        if not pdf_url and arxiv_id:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
        results.append({
            "arxiv_id": arxiv_id,
            "title": title,
            "authors": authors,
            "summary": summary,
            "pdf_url": pdf_url,
            "published": published,
        })
    return results


def _safe_filename(title: str, arxiv_id: str) -> str:
    base = re.sub(r"[^\w一-鿿 -]", "", title).strip().replace(" ", "_")
    base = base[:60] or "paper"
    short_id = arxiv_id.replace("/", "_")
    return f"{base}_{short_id}.pdf"


def download_paper(entry: dict, dest_dir: str = "papers") -> str:
    """下载单篇论文 PDF 到 dest_dir，返回保存路径。"""
    d = Path(dest_dir)
    d.mkdir(parents=True, exist_ok=True)
    out = d / _safe_filename(entry["title"], entry["arxiv_id"])
    if out.exists():
        print(f"  已存在，跳过：{out.name}")
        return str(out)
    req = urllib.request.Request(entry["pdf_url"], headers=_UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    out.write_bytes(data)
    print(f"  已下载：{out.name}（{len(data)//1024} KB）")
    time.sleep(1)  # 对 arXiv 友好，避免过快请求
    return str(out)


def _print_results(results: list[dict]) -> None:
    for i, r in enumerate(results, 1):
        authors = ", ".join(r["authors"][:3]) + ("等" if len(r["authors"]) > 3 else "")
        print(f"\n[{i}] {r['title']}")
        print(f"    {authors} | {r['published']} | {r['arxiv_id']}")
        print(f"    {r['summary'][:200]}...")


def _main(argv: list[str]) -> None:
    if not argv:
        print('用法：python -m src.arxiv_search "查询词" [--max N] [--download all|1,2,3]')
        return
    # 解析参数
    query_parts, max_results, download = [], 10, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--max":
            max_results = int(argv[i + 1]); i += 2; continue
        if a == "--download":
            download = argv[i + 1]; i += 2; continue
        query_parts.append(a); i += 1
    query = " ".join(query_parts)

    print(f"在 arXiv 检索：{query}")
    results = search_arxiv(query, max_results=max_results)
    if not results:
        print("没有找到结果。")
        return
    _print_results(results)

    if download:
        if download.lower() == "all":
            picks = list(range(len(results)))
        else:
            picks = [int(x) - 1 for x in download.split(",") if x.strip().isdigit()]
        print("\n开始下载到 papers/ ...")
        for idx in picks:
            if 0 <= idx < len(results):
                download_paper(results[idx])
        print("\n完成。可运行 `python app.py --library` 重新索引论文库。")
    else:
        print('\n如需下载，加 --download all 或 --download 1,3,5')


if __name__ == "__main__":
    _main(sys.argv[1:])

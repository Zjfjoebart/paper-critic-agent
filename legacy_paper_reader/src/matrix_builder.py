"""
matrix_builder.py
Literature Matrix 生成器。

流程：
1. 对每篇论文，分别用 retriever 检索关键维度的证据
2. 调用 DeepSeek 从证据中提取结构化字段
3. 汇总为 Markdown 表格 + CSV 文件

支持的字段（可按需扩展）：
  标题 / 方法名 / 发表年份 / 任务类型 / 模型基座
  数据集 / 核心指标 / 核心结果 / 压缩率/加速比
  核心创新 / 主要局限
"""

import asyncio
import csv
import json
import re
from datetime import datetime
from pathlib import Path

from openai import AsyncOpenAI
import os


# 要提取的字段及对应的检索 query
FIELDS = [
    ("标题",       "paper title"),
    ("方法名",     "method name proposed approach"),
    ("发表年份",   "published year arxiv submission"),
    ("任务类型",   "task setting problem formulation"),
    ("模型基座",   "base model backbone LLM VLM"),
    ("数据集",     "datasets evaluation benchmark"),
    ("核心指标",   "evaluation metrics accuracy performance"),
    ("核心结果",   "main results performance numbers table"),
    ("压缩/加速比","compression ratio token reduction speedup"),
    ("核心创新",   "key contribution novelty innovation"),
    ("主要局限",   "limitation weakness future work"),
]


async def _extract_field_for_paper(
    client: AsyncOpenAI,
    field_name: str,
    evidence: str,
    paper_name: str,
) -> str:
    """
    用 DeepSeek 从检索到的证据中提取单个字段值。
    返回简短的字段值字符串（< 80 字）。
    """
    prompt = f"""你正在为论文「{paper_name}」提取文献矩阵中的一个字段。

字段名：{field_name}
以下是从论文中检索到的相关原文片段：

{evidence}

请从上述原文中提取「{field_name}」的值。
要求：
- 简洁，不超过 80 字
- 尽量使用原文中的术语
- 如果原文中找不到明确信息，回答"未明确"
- 不要解释，直接输出字段值

字段值："""

    resp = await client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=150,
        temperature=0.1,
    )
    return resp.choices[0].message.content.strip()


async def build_matrix(
    retriever,  # MultiPaperRetriever
    output_dir: str = ".",
) -> tuple[str, str]:
    """
    生成 Literature Matrix。

    Args:
        retriever: MultiPaperRetriever 实例
        output_dir: 输出目录

    Returns:
        (markdown_path, csv_path)
    """
    client = AsyncOpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )

    papers = list(retriever.papers.values())
    print(f"\n[Matrix] 开始为 {len(papers)} 篇论文生成 Literature Matrix...")

    # 收集所有论文的所有字段
    rows: list[dict] = []
    for paper_info in papers:
        pid = paper_info["paper_id"]
        name = paper_info["name"]
        print(f"\n  处理：{name}")

        row = {"论文": name}
        for field_name, query in FIELDS:
            # 检索该字段的证据
            results = retriever.hybrid_search(query, top_k=3, paper_id=pid)
            if results:
                evidence = "\n\n".join(
                    f"[p.{r['page']}] {r['text'][:400]}" for r in results
                )
            else:
                evidence = "（未找到相关段落）"

            # 用 LLM 提取字段值
            value = await _extract_field_for_paper(client, field_name, evidence, name)
            row[field_name] = value
            print(f"    {field_name}: {value[:50]}{'...' if len(value) > 50 else ''}")

        rows.append(row)

    # 生成 Markdown 表格
    field_names = ["论文"] + [f for f, _ in FIELDS]
    md_lines = []
    md_lines.append("# Literature Matrix")
    md_lines.append(f"\n生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    md_lines.append("| " + " | ".join(field_names) + " |")
    md_lines.append("| " + " | ".join(["---"] * len(field_names)) + " |")
    for row in rows:
        cells = [row.get(f, "—") for f in field_names]
        # 清理单元格中的换行
        cells = [c.replace("\n", " ").replace("|", "｜") for c in cells]
        md_lines.append("| " + " | ".join(cells) + " |")

    # 附加：各字段完整值（宽表格单元格太窄看不清时用）
    md_lines.append("\n---\n## 字段详情\n")
    for row in rows:
        md_lines.append(f"### {row['论文']}\n")
        for field_name, _ in FIELDS:
            md_lines.append(f"**{field_name}**：{row.get(field_name, '—')}\n")
        md_lines.append("")

    md_content = "\n".join(md_lines)

    # 写文件
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    md_path = out / f"literature_matrix_{ts}.md"
    csv_path = out / f"literature_matrix_{ts}.csv"

    md_path.write_text(md_content, encoding="utf-8")

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=field_names)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n[Matrix] 完成！")
    print(f"  Markdown → {md_path}")
    print(f"  CSV      → {csv_path}")

    return str(md_path), str(csv_path)

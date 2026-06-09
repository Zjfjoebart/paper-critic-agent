"""
commands.py
会话内命令的共享逻辑（find / viz / matrix），供简易 CLI 与富 CLI 共用。
不依赖具体界面，只做事并返回/打印结果。
"""

import csv as _csv

VIZ_DIR = "outputs"


async def do_find(query: str, state: dict, echo=print) -> list:
    """联网搜索相关论文，存入 state['last_results']，并生成研究图景图。返回结果列表。"""
    from src.paper_finder import find_papers, format_results
    from src.visualize import viz_landscape

    echo(f"联网搜索：{query}")
    try:
        results = find_papers(query, limit=15)
    except Exception as e:
        echo(f"[错误] 搜索失败：{e}")
        return []
    echo(format_results(results))
    state["last_results"] = results
    state["last_query"] = query
    if results:
        html = viz_landscape(results, out_dir=VIZ_DIR, query=query)
        echo(f"\n研究图景已生成：{html}（用浏览器打开）")
    return results


def do_viz(state: dict, echo=print) -> str | None:
    """重新生成上次搜索结果的研究图景图。"""
    from src.visualize import viz_landscape
    results = state.get("last_results")
    if not results:
        echo("[提示] 还没有搜索结果。先用 find <关键词> 联网搜索。")
        return None
    html = viz_landscape(results, out_dir=VIZ_DIR, query=state.get("last_query", ""))
    echo(f"研究图景已生成：{html}")
    return html


async def do_matrix(retriever, echo=print):
    """生成 Literature Matrix（MD+CSV）并附带指标对比图。"""
    from src.matrix_builder import build_matrix
    from src.visualize import viz_metrics
    try:
        md_path, csv_path = await build_matrix(retriever, output_dir=VIZ_DIR)
        echo(f"\n文件已保存：\n  {md_path}\n  {csv_path}")
        with open(csv_path, encoding="utf-8-sig") as f:
            rows = list(_csv.DictReader(f))
        html = viz_metrics(rows, fields=["发表年份", "核心指标", "压缩/加速比"], out_dir=VIZ_DIR)
        if html:
            echo(f"  指标对比图：{html}（用浏览器打开）")
        else:
            echo("  （未从矩阵字段中解析到可对比的数字，跳过指标图）")
    except Exception as e:
        echo(f"[错误] {type(e).__name__}: {e}")

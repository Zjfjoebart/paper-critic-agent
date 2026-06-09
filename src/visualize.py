"""
visualize.py
生成可在浏览器打开的交互式 HTML 图表（Chart.js，CDN 加载，无 Python 依赖）。

两类图：
1. 研究图景 viz_landscape：搜索到的论文按 年份 × 引用数 画气泡散点，
   悬停看标题/会议/作者，直观看一个方向的热度与增长趋势。
2. 指标对比 viz_metrics：从 Literature Matrix 的某个数字字段提取数值，
   做成论文间对比柱状图。
"""

import json
import re
from datetime import datetime
from pathlib import Path

_CHARTJS = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"

_PAGE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<script src="{cdn}"></script>
<style>
  body{{font-family:-apple-system,Segoe UI,Arial,sans-serif;margin:24px;color:#222;background:#fafafa}}
  h1{{font-size:20px;color:#2E6DA4}} .sub{{color:#888;font-size:13px;margin-bottom:18px}}
  .card{{background:#fff;border:1px solid #eee;border-radius:10px;padding:18px;margin-bottom:22px;
        box-shadow:0 1px 3px rgba(0,0,0,.05)}}
  canvas{{max-height:480px}}
</style></head>
<body>
<h1>{title}</h1><div class="sub">生成时间：{ts}</div>
{cards}
<script>{scripts}</script>
</body></html>"""


def _write(out_dir: str, name: str, title: str, cards: str, scripts: str) -> str:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = _PAGE.format(title=title, cdn=_CHARTJS, ts=ts, cards=cards, scripts=scripts)
    path = Path(out_dir) / name
    path.write_text(html, encoding="utf-8")
    return str(path)


def viz_landscape(results: list[dict], out_dir: str = "outputs",
                  query: str = "") -> str:
    """
    研究图景：年份(x) × 引用数(y) 气泡散点。气泡大小同样反映引用数。
    results: paper_finder.find_papers 的返回。
    """
    points = []
    for r in results:
        if not r.get("year"):
            continue
        c = r.get("citations") or 0
        points.append({
            "x": r["year"],
            "y": c,
            "r": max(5, min(28, (c ** 0.5))),  # 气泡半径，开方压缩
            "title": r.get("title", ""),
            "venue": r.get("venue", "") or "—",
            "top": bool(r.get("is_top")),
        })

    top = [p for p in points if p["top"]]
    other = [p for p in points if not p["top"]]
    data_js = json.dumps({"top": top, "other": other}, ensure_ascii=False)

    cards = '<div class="card"><canvas id="c1"></canvas></div>'
    scripts = """
const D = %s;
new Chart(document.getElementById('c1'), {
  type: 'bubble',
  data: { datasets: [
    { label: '顶会/顶刊', data: D.top, backgroundColor: 'rgba(46,109,164,.6)' },
    { label: '其他', data: D.other, backgroundColor: 'rgba(180,180,180,.5)' },
  ]},
  options: {
    plugins: {
      title: { display: true, text: '研究图景：年份 × 引用数%s' },
      tooltip: { callbacks: { label: (ctx) => {
        const p = ctx.raw;
        return [p.title, p.venue + ' · ' + p.x + ' · 引用 ' + p.y];
      }}}
    },
    scales: {
      x: { title: { display: true, text: '发表年份' }, ticks: { precision: 0 } },
      y: { title: { display: true, text: '引用数' }, beginAtZero: true }
    }
  }
});
""" % (data_js, (f"（{query}）" if query else ""))

    safe = re.sub(r"[^\w-]", "_", query)[:30] or "papers"
    return _write(out_dir, f"landscape_{safe}.html", "研究图景", cards, scripts)


def _extract_number(text: str):
    """从字段文本里抓第一个数字（支持百分比/小数），抓不到返回 None。"""
    if not text:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    return float(m.group()) if m else None


def viz_metrics(rows: list[dict], fields: list[str], out_dir: str = "outputs") -> str | None:
    """
    指标对比：从 Literature Matrix 行中，对每个数字字段抽取数值，画论文间对比柱状图。
    rows: [{"论文": name, "<字段>": "值文本", ...}, ...]
    fields: 要尝试可视化的字段名列表（如 ["核心指标","压缩/加速比"]）。
    若没有任何可解析的数字，返回 None。
    """
    labels = [r.get("论文", f"paper{i}") for i, r in enumerate(rows)]
    charts = []
    any_data = False

    for field in fields:
        values = [_extract_number(r.get(field, "")) for r in rows]
        if not any(v is not None for v in values):
            continue
        any_data = True
        charts.append({
            "field": field,
            "labels": labels,
            "values": [v if v is not None else 0 for v in values],
        })

    if not any_data:
        return None

    cards, scripts = [], []
    for i, ch in enumerate(charts):
        cards.append(f'<div class="card"><canvas id="m{i}"></canvas></div>')
        scripts.append("""
new Chart(document.getElementById('m%d'), {
  type: 'bar',
  data: { labels: %s, datasets: [{ label: %s, data: %s,
          backgroundColor: 'rgba(46,109,164,.7)' }]},
  options: { plugins: { title: { display: true, text: '指标对比：%s' } },
             scales: { y: { beginAtZero: true } } }
});""" % (
            i,
            json.dumps(ch["labels"], ensure_ascii=False),
            json.dumps(ch["field"], ensure_ascii=False),
            json.dumps(ch["values"]),
            ch["field"],
        ))

    return _write(out_dir, "metrics_compare.html", "指标对比",
                  "\n".join(cards), "\n".join(scripts))

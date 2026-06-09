"""
result_tools.py
读取结果、汇总指标、检测异常（Layer 1，纯 Python）。
所有"判断实验是否完成/算平均/比大小"都在这里用代码确定性完成，不交给 LLM。
"""

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean


def read_result(result_path: str) -> dict:
    """读取单个 result json，返回 metrics（无则空 dict）。"""
    try:
        data = json.loads(Path(result_path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data.get("metrics", {}) or {}


def find_missing_runs(expected: list[dict], ledger: list) -> list[dict]:
    """返回 status == 'missing' 的期望实验。"""
    done_ids = {e.run_id for e in ledger if e.status != "missing"}
    return [r for r in expected if r["run_id"] not in done_ids]


def summarize_results(ledger: list) -> list[dict]:
    """
    按 (model, task, method, keep_ratio) 汇总 finished 实验的 accuracy / drop（多 seed 取均值）。
    Returns: [{model, task, method, keep_ratio, n, accuracy, drop}, ...]
    """
    groups = defaultdict(list)
    for e in ledger:
        if e.status == "finished" and "accuracy" in (e.metrics or {}):
            key = (e.model, e.task, e.method, e.keep_ratio)
            groups[key].append(e.metrics)
    rows = []
    for (model, task, method, keep), ms in sorted(groups.items(), key=lambda x: str(x[0])):
        accs = [m["accuracy"] for m in ms if "accuracy" in m]
        drops = [m["drop"] for m in ms if "drop" in m]
        rows.append({
            "model": model, "task": task, "method": method, "keep_ratio": keep,
            "n": len(ms),
            "accuracy": round(mean(accs), 4) if accs else None,
            "drop": round(mean(drops), 4) if drops else None,
        })
    return rows


def detect_anomalies(ledger: list) -> list[dict]:
    """
    规则化异常检测（只看 finished + 有 accuracy 的实验）。
    规则：
      1. 某方法比 random 还差（同 model/task/keep）
      2. oracle 低于 attention（同 model/task/keep）
      3. keep_ratio 越高 accuracy 反而越低（同 model/task/method）
    Returns: [{type, scope, detail}, ...]
    """
    # 建索引：acc[(model,task,method,keep)] = accuracy
    acc = {}
    for e in ledger:
        if e.status == "finished" and "accuracy" in (e.metrics or {}):
            acc[(e.model, e.task, e.method, e.keep_ratio)] = e.metrics["accuracy"]

    anomalies = []

    # 1 & 2：同 (model,task,keep) 下比较方法
    cells = defaultdict(dict)  # (model,task,keep) -> {method: acc}
    for (m, t, me, k), a in acc.items():
        cells[(m, t, k)][me] = a
    for (m, t, k), md in cells.items():
        base = md.get("random")
        if base is not None:
            for me, a in md.items():
                if me != "random" and a < base:
                    anomalies.append({
                        "type": "WorseThanRandom",
                        "scope": f"{m} / {t} / keep={k}",
                        "detail": f"{me} acc={a} < random acc={base}",
                    })
        if "oracle" in md and "attention" in md and md["oracle"] < md["attention"]:
            anomalies.append({
                "type": "OracleBelowAttention",
                "scope": f"{m} / {t} / keep={k}",
                "detail": f"oracle acc={md['oracle']} < attention acc={md['attention']}",
            })

    # 3：同 (model,task,method) 下 keep 越高 acc 越低
    series = defaultdict(list)  # (model,task,method) -> [(keep, acc)]
    for (m, t, me, k), a in acc.items():
        series[(m, t, me)].append((k, a))
    for (m, t, me), pts in series.items():
        pts.sort(key=lambda x: x[0])
        for (k1, a1), (k2, a2) in zip(pts, pts[1:]):
            if a2 < a1 - 1e-9:
                anomalies.append({
                    "type": "KeepRatioNonMonotonic",
                    "scope": f"{m} / {t} / {me}",
                    "detail": f"keep {k1}->{k2} 时 acc {a1}->{a2}（更高保留率反而更低）",
                })
    return anomalies

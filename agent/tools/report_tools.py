"""
report_tools.py
把确定性结果写成派生文件（Layer 1，写入 outputs/）。
  - experiment_status.md   阶段性报告
  - missing_runs.csv       缺失实验
  - failed_runs.csv        失败实验
  - next_commands.sh       下一批命令
"""

import csv
from datetime import datetime
from pathlib import Path


def _counts(ledger):
    c = {"finished": 0, "failed": 0, "pending": 0, "missing": 0}
    for e in ledger:
        c[e.status] = c.get(e.status, 0) + 1
    return c


def write_missing_csv(missing: list[dict], out_dir: str) -> str:
    path = Path(out_dir) / "missing_runs.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["run_id", "model", "task", "method", "keep_ratio", "seed"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in missing:
            w.writerow({k: r.get(k) for k in fields})
    return str(path)


def write_failed_csv(ledger, out_dir: str) -> str:
    path = Path(out_dir) / "failed_runs.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["run_id", "model", "task", "method", "keep_ratio", "error_type", "log_path"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for e in ledger:
            if e.status == "failed":
                w.writerow({"run_id": e.run_id, "model": e.model, "task": e.task,
                            "method": e.method, "keep_ratio": e.keep_ratio,
                            "error_type": e.error_type, "log_path": e.log_path})
    return str(path)


def write_next_commands(commands: list[str], out_dir: str) -> str:
    path = Path(out_dir) / "next_commands.sh"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "#!/usr/bin/env bash\n# 由 ResearchOps 自动生成；执行前请人工核对\nset -e\n\n" + "\n".join(commands) + "\n"
    path.write_text(body, encoding="utf-8")
    return str(path)


def write_status_report(ledger, summary_rows, anomalies, failed_breakdown,
                        out_dir: str, project: str = "") -> str:
    """生成 experiment_status.md。严格区分『已验证 / 尚未验证』。"""
    path = Path(out_dir) / "experiment_status.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    c = _counts(ledger)
    total = len(ledger)
    L = []
    L.append(f"# 实验状态报告{(' — ' + project) if project else ''}")
    L.append(f"\n生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    L.append("## 1. 完成度")
    L.append(f"\n期望实验 **{total}** 个：完成 {c['finished']} · 失败 {c['failed']} · "
             f"进行中/未完成 {c['pending']} · 缺失 {c['missing']}\n")

    L.append("## 2. 失败原因分布")
    if failed_breakdown:
        L.append("")
        for et, items in failed_breakdown.items():
            L.append(f"- **{et}**：{len(items)} 个（{', '.join(items[:4])}{' …' if len(items) > 4 else ''}）")
        L.append("")
    else:
        L.append("\n无失败实验。\n")

    L.append("## 3. 主要结果（已完成实验汇总）")
    if summary_rows:
        L.append("\n| model | task | method | keep | n | accuracy | drop |")
        L.append("| --- | --- | --- | --- | --- | --- | --- |")
        for r in summary_rows:
            L.append(f"| {r['model']} | {r['task']} | {r['method']} | {r['keep_ratio']} "
                     f"| {r['n']} | {r['accuracy']} | {r['drop']} |")
        L.append("")
    else:
        L.append("\n暂无可汇总的完成实验。\n")

    L.append("## 4. 异常结果")
    if anomalies:
        L.append("")
        for a in anomalies:
            L.append(f"- **{a['type']}** @ {a['scope']}：{a['detail']}")
        L.append("")
    else:
        L.append("\n未检测到规则内异常。\n")

    L.append("## 5. 证据边界")
    L.append("\n**已验证**：上表中 status=finished 且含 accuracy 的实验结果。")
    L.append(f"\n**尚未验证**：{c['missing']} 个缺失 + {c['pending']} 个未完成 + "
             f"{c['failed']} 个失败的组合，其结论暂不能下。\n")

    L.append("## 6. 下一步优先级（确定性建议）")
    L.append("\n1. 先修失败实验（见失败原因分布），再重跑。")
    L.append("2. 补齐缺失实验（见 missing_runs.csv / next_commands.sh）。")
    L.append("3. 复核异常结果对应的 run，确认非配置/数据问题。\n")

    path.write_text("\n".join(L), encoding="utf-8")
    return str(path)

"""
pipeline.py
第 1 层主流程：把确定性步骤串起来，产出 outputs/ 下的派生文件。
被 CLI（status 命令）和 LLM Agent 共同复用。
"""

from collections import defaultdict
from pathlib import Path

from agent.state import build_ledger, write_ledger_csv
from agent.tools.config_tools import load_grid, build_experiment_matrix
from agent.tools.result_tools import find_missing_runs, summarize_results, detect_anomalies
from agent.tools.command_tools import generate_commands
from agent.tools import report_tools


def _write_generated_configs(missing: list[dict], out_dir: str) -> str:
    """为缺失实验生成 config（Config Planner），写到 outputs/generated_configs/，不动 workspace。"""
    d = Path(out_dir) / "generated_configs"
    d.mkdir(parents=True, exist_ok=True)
    for r in missing:
        (d / f"{r['run_id']}.yaml").write_text(
            f"run_id: {r['run_id']}\nmodel: {r['model']}\ntask: {r['task']}\n"
            f"method: {r['method']}\nkeep_ratio: {r['keep_ratio']}\nseed: {r['seed']}\n",
            encoding="utf-8")
    return str(d)


def run_status(workspace: str, grid_path: str | None = None,
               out_dir: str = "outputs", project: str = "") -> dict:
    """
    扫描项目 → 建账本 → 计算 missing/failed/汇总/异常 → 写派生文件。
    返回一个结构化摘要（供 CLI 打印 / LLM 解释）。
    """
    ws = Path(workspace)
    grid_path = grid_path or str(ws / "grid.yaml")
    grid = load_grid(grid_path)
    project = project or ws.name

    ledger = build_ledger(workspace, grid_path, project=project)
    expected = build_experiment_matrix(grid)
    missing = find_missing_runs(expected, ledger)
    summary_rows = summarize_results(ledger)
    anomalies = detect_anomalies(ledger)

    failed_breakdown = defaultdict(list)
    for e in ledger:
        if e.status == "failed":
            failed_breakdown[e.error_type or "Unknown"].append(e.run_id)

    # 为缺失实验生成 config + 下一批命令
    gen_dir = _write_generated_configs(missing, out_dir)
    template = grid.get("command_template", "python eval.py --config {config}")
    commands = generate_commands(missing, template, configs_dir=gen_dir)

    # 写派生文件
    ledger_csv = write_ledger_csv(ledger, out_dir)
    missing_csv = report_tools.write_missing_csv(missing, out_dir)
    failed_csv = report_tools.write_failed_csv(ledger, out_dir)
    cmds_sh = report_tools.write_next_commands(commands, out_dir)
    report_md = report_tools.write_status_report(
        ledger, summary_rows, anomalies, dict(failed_breakdown), out_dir, project=project)

    counts = defaultdict(int)
    for e in ledger:
        counts[e.status] += 1

    return {
        "project": project,
        "total": len(ledger),
        "counts": dict(counts),
        "missing": missing,
        "failed_breakdown": dict(failed_breakdown),
        "anomalies": anomalies,
        "summary_rows": summary_rows,
        "outputs": {
            "experiments_csv": ledger_csv,
            "missing_csv": missing_csv,
            "failed_csv": failed_csv,
            "next_commands_sh": cmds_sh,
            "status_md": report_md,
            "generated_configs": gen_dir,
        },
    }

"""
state.py
实验账本（Experiment Ledger）——整个系统最重要的数据结构。
把每个实验统一成一条记录，避免 Agent 变成临时读 log 的脚本。
第一版用 CSV 持久化，足够；后续可换 SQLite / MLflow。
"""

import csv
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from agent.tools.config_tools import build_experiment_matrix, load_grid
from agent.tools.result_tools import read_result
from agent.tools.log_tools import parse_log


@dataclass
class Experiment:
    run_id: str
    project: str = ""
    model: str = ""
    task: str = ""
    method: str = ""
    keep_ratio: float | None = None
    seed: int | None = None
    config_path: str | None = None
    log_path: str | None = None
    result_path: str | None = None
    status: str = "missing"          # finished / failed / pending / missing
    metrics: dict = field(default_factory=dict)
    error_type: str | None = None


def build_ledger(workspace: str, grid_path: str, project: str = "") -> list[Experiment]:
    """
    结合 期望矩阵 + configs + logs + results，确定每个实验的状态，返回账本。
    状态判定（确定性，全部由代码完成）：
      finished : result 含 accuracy
      failed   : 日志报错 / 评测完成但缺指标 / 有 result 但无 accuracy
      pending  : 有 config 但没 result、也没失败日志（在跑或没跑完）
      missing  : config/log/result 都没有
    """
    ws = Path(workspace)
    expected = build_experiment_matrix(load_grid(grid_path))
    ledger = []
    for r in expected:
        rid = r["run_id"]
        cfg = ws / "configs" / f"{rid}.yaml"
        log = ws / "logs" / f"{rid}.log"
        rez = ws / "results" / f"{rid}.json"

        metrics = read_result(str(rez)) if rez.exists() else {}
        has_metric = bool(metrics) and "accuracy" in metrics
        log_info = parse_log(str(log)) if log.exists() else None

        if has_metric:
            status, error_type = "finished", None
        elif log_info and log_info["error_type"]:
            status, error_type = "failed", log_info["error_type"]
        elif log_info and (log_info["metric_missing"] or log_info["finished"]) or (rez.exists() and not has_metric):
            status, error_type = "failed", "MetricMissing"
        elif cfg.exists():
            status, error_type = "pending", None
        else:
            status, error_type = "missing", None

        ledger.append(Experiment(
            run_id=rid, project=project,
            model=r.get("model", ""), task=r.get("task", ""),
            method=r.get("method", ""), keep_ratio=r.get("keep_ratio"),
            seed=r.get("seed"),
            config_path=str(cfg) if cfg.exists() else None,
            log_path=str(log) if log.exists() else None,
            result_path=str(rez) if rez.exists() else None,
            status=status, metrics=metrics, error_type=error_type,
        ))
    return ledger


def write_ledger_csv(ledger: list[Experiment], out_dir: str) -> str:
    path = Path(out_dir) / "experiments.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["run_id", "project", "model", "task", "method", "keep_ratio", "seed",
              "status", "error_type", "accuracy", "drop", "config_path", "log_path", "result_path"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for e in ledger:
            row = asdict(e)
            row["accuracy"] = (e.metrics or {}).get("accuracy")
            row["drop"] = (e.metrics or {}).get("drop")
            w.writerow({k: row.get(k) for k in fields})
    return str(path)

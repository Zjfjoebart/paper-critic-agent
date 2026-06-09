"""
config_tools.py
读取实验配置 + 由 grid 生成期望实验矩阵（Layer 1，纯 Python）。
"""

import itertools
from pathlib import Path

import yaml


# run_id 命名规则（务必与生成/检索一致）：
#   {model}_{task}_{method}_k{keep*100:02d}_s{seed}
AXES = ["model", "task", "method", "keep_ratio", "seed"]


def make_run_id(model, task, method, keep_ratio, seed) -> str:
    return f"{model}_{task}_{method}_k{int(round(float(keep_ratio) * 100)):02d}_s{seed}"


def read_config(config_path: str) -> dict:
    """解析单个实验配置（yaml 或 json）。"""
    p = Path(config_path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        import json
        return json.loads(text)
    return yaml.safe_load(text) or {}


def load_grid(grid_path: str) -> dict:
    """读取实验矩阵定义 grid.yaml。"""
    return yaml.safe_load(Path(grid_path).read_text(encoding="utf-8")) or {}


def build_experiment_matrix(grid: dict) -> list[dict]:
    """
    由 grid 的各维度笛卡尔积生成期望实验列表。
    grid 形如 {model:[...], task:[...], method:[...], keep_ratio:[...], seed:[...]}。

    Returns:
        [{"run_id":..., "model":..., "task":..., "method":..., "keep_ratio":..., "seed":...}, ...]
    """
    axes_vals = []
    for ax in AXES:
        v = grid.get(ax, [])
        if not isinstance(v, list):
            v = [v]
        axes_vals.append(v or [None])

    runs = []
    for combo in itertools.product(*axes_vals):
        d = dict(zip(AXES, combo))
        d["run_id"] = make_run_id(d["model"], d["task"], d["method"], d["keep_ratio"], d["seed"])
        runs.append(d)
    return runs

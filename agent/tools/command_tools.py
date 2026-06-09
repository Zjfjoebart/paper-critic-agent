"""
command_tools.py
生成下一批可执行命令 / 受控执行命令（Layer 1 + 安全）。
默认 dry_run=True：只生成、不执行。真正执行须经 safety 人工确认。
"""

import subprocess
from pathlib import Path


def generate_commands(missing_or_failed: list[dict], command_template: str,
                      configs_dir: str = "workspace/configs") -> list[str]:
    """
    为缺失/需重跑的实验生成命令。
    command_template 形如 "python eval.py --config {config}"。
    """
    cmds = []
    for r in missing_or_failed:
        run_id = r["run_id"] if isinstance(r, dict) else r
        config_path = str(Path(configs_dir) / f"{run_id}.yaml")
        cmds.append(command_template.format(config=config_path, run_id=run_id))
    return cmds


def run_command(command: str, dry_run: bool = True) -> dict:
    """
    执行单条命令。dry_run=True（默认）只回显不执行。
    真正执行请由上层在取得人工确认后调用 dry_run=False。
    """
    if dry_run:
        return {"command": command, "executed": False, "note": "dry-run，未执行"}
    proc = subprocess.run(command, shell=True, capture_output=True, text=True)
    return {
        "command": command,
        "executed": True,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-2000:],
        "stderr": proc.stderr[-2000:],
    }

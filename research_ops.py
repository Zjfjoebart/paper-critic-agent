"""
research_ops.py
ResearchOps Agent — 面向科研实验的自动化管理助手。

第 1 层（确定性，不接 LLM）：
    python research_ops.py status --workspace examples/vision_token_compression

第 2/3 层（接入 LLM 的对话式界面）：
    python research_ops.py chat --workspace examples/vision_token_compression

设计原则：文件统计 / 指标计算 / 完成判定全部由 Python 确定性完成；
LLM 只负责解释异常、写报告、建议下一步——不让大模型去数文件、算平均。
"""

import argparse
import os
import sys
from pathlib import Path

DEFAULT_WS = os.environ.get("RESEARCHOPS_WORKSPACE", "workspace")

from agent.pipeline import run_status


def _print_status(res: dict):
    c = res["counts"]
    print("\n" + "=" * 60)
    print(f"实验状态 · {res['project']}")
    print("=" * 60)
    print(f"期望实验 {res['total']} 个：完成 {c.get('finished',0)} · 失败 {c.get('failed',0)} · "
          f"进行中 {c.get('pending',0)} · 缺失 {c.get('missing',0)}")

    if res["failed_breakdown"]:
        print("\n失败原因：")
        for et, ids in res["failed_breakdown"].items():
            print(f"  {et}: {len(ids)}  ({', '.join(ids[:3])}{' …' if len(ids)>3 else ''})")

    if res["anomalies"]:
        print(f"\n异常结果 {len(res['anomalies'])} 处：")
        for a in res["anomalies"]:
            print(f"  [{a['type']}] {a['scope']} — {a['detail']}")

    if res["missing"]:
        print(f"\n缺失实验 {len(res['missing'])} 个（详见 missing_runs.csv）")

    print("\n已生成：")
    for k, v in res["outputs"].items():
        print(f"  {v}")
    print("=" * 60)


def cmd_status(args):
    ws = args.workspace
    if not Path(ws).is_dir():
        print(f"[错误] workspace 不存在：{ws}")
        sys.exit(1)
    res = run_status(ws, grid_path=args.grid, out_dir=args.out, project=getattr(args, "project", "") or "")
    _print_status(res)


def cmd_chat(args):
    if not Path(args.workspace).is_dir():
        print(f"[错误] workspace 不存在：{args.workspace}")
        sys.exit(1)
    try:
        import asyncio
        from agent.cli import run_chat
        asyncio.run(run_chat(args.workspace, grid_path=args.grid, out_dir=args.out))
    except ImportError as e:
        print(f"[提示] 对话式界面需要 rich / prompt_toolkit / openai-agents（{e}），"
              "先以只读方式显示当前实验状态：\n")
        cmd_status(args)


def main():
    p = argparse.ArgumentParser(prog="research_ops", description="ResearchOps Agent")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("status", help="扫描项目并输出实验状态（确定性，不接 LLM）")
    ps.add_argument("--workspace", "-w", default=DEFAULT_WS, help="实验项目目录")
    ps.add_argument("--grid", default=None, help="实验矩阵定义（默认 <workspace>/grid.yaml）")
    ps.add_argument("--out", default="outputs", help="派生文件输出目录")
    ps.add_argument("--project", default="", help="项目名（默认取目录名）")
    ps.set_defaults(func=cmd_status)

    pc = sub.add_parser("chat", help="对话式界面（接入 LLM，解释/报告/建议）")
    pc.add_argument("--workspace", "-w", default=DEFAULT_WS)
    pc.add_argument("--grid", default=None)
    pc.add_argument("--out", default="outputs")
    pc.set_defaults(func=cmd_chat)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

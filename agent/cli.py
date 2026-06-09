"""
cli.py
第 3 层：ResearchOps 的 Claude Code 风格对话界面（rich + prompt_toolkit）。
命令：/status /report /run /model /clear /exit；直接提问交给 LLM 解释/建议。
"""

import os
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live
from rich.spinner import Spinner

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML

from agent.main_agent import build_status_agent, ask_agent, ask_agent_stream
from agent.pipeline import run_status
from agent.tools.command_tools import run_command
from agent.safety import confirm_execution

console = Console()

SLASH = {
    "/status": "重新扫描并打印实验状态",
    "/report": "显示已生成的报告路径",
    "/run": "执行 next_commands.sh（需人工确认，Level 2）",
    "/model": "切换推理模型",
    "/clear": "清空对话记忆 + 清屏",
    "/exit": "退出",
}
MODELS = ["deepseek-chat", "deepseek-reasoner"]

BANNER = """[bold #2E6DA4]ResearchOps Agent[/]  ·  科研实验管理助手

直接提问（会记住上下文），或用 [bold]/[/] 命令（Tab 补全）。
[bold]/status[/] 看状态 · [bold]/report[/] 报告 · [bold]/run[/] 执行命令(需确认) · [bold]/model[/] 换模型 · [bold]/exit[/] 退出
确定性统计由代码完成，LLM 只做解释、判断证据、建议下一步。"""


def _toolbar(workspace, model, counts):
    c = counts or {}
    s = f" 完成{c.get('finished',0)}/失败{c.get('failed',0)}/缺失{c.get('missing',0)}"
    return HTML(f" <b>项目</b> {Path(workspace).name} ·{s} · <b>模型</b> {model} · Tab 补全 · Ctrl-C 退出")


def _print_status(res):
    c = res["counts"]
    console.print(Panel(
        f"期望 {res['total']} · 完成 {c.get('finished',0)} · 失败 {c.get('failed',0)} · "
        f"进行中 {c.get('pending',0)} · 缺失 {c.get('missing',0)}\n"
        f"失败分布：{res['failed_breakdown'] or '无'}\n"
        f"异常：{len(res['anomalies'])} 处\n"
        f"报告：{res['outputs']['status_md']}",
        title=f"实验状态 · {res['project']}", border_style="#2E6DA4", expand=False))


async def _answer(agent, question, history):
    try:
        buf = {"t": ""}
        with Live(console=console, refresh_per_second=12, vertical_overflow="visible") as live:
            live.update(Spinner("dots", text=" 分析中…", style="#2E6DA4"))

            def on_delta(d):
                buf["t"] += d
                live.update(Markdown(buf["t"]))

            full, new_history = await ask_agent_stream(agent, question, on_delta, history)
            if not buf["t"]:
                live.update(Markdown(full or "（无内容）"))
        return new_history
    except Exception:
        pass
    with console.status(" 分析中…", spinner="dots", spinner_style="#2E6DA4"):
        answer, new_history = await ask_agent(agent, question, history)
    console.print(Markdown(answer))
    return new_history


def _read_commands(out_dir):
    p = Path(out_dir) / "next_commands.sh"
    if not p.exists():
        return []
    cmds = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and ln != "set -e":
            cmds.append(ln)
    return cmds


async def run_chat(workspace: str, grid_path: str | None = None, out_dir: str = "outputs"):
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    res = run_status(workspace, grid_path=grid_path, out_dir=out_dir)
    console.print(Panel(BANNER, border_style="#2E6DA4", expand=False))
    _print_status(res)

    # 没有 API key：只读窗口，仅展示当前实验内容，不进入对话
    if not os.environ.get("DEEPSEEK_API_KEY"):
        console.print("[yellow]未配置 DEEPSEEK_API_KEY —— 当前为只读模式，已显示实验状态。[/]\n"
                      "[dim]在 .env 填入 key 后，重新运行即可对话（解释失败、建议下一步等）。[/]")
        return

    agent = build_status_agent(workspace, grid_path, out_dir, model=model)

    session = PromptSession(
        history=InMemoryHistory(),
        completer=WordCompleter(list(SLASH) + ["status", "report", "run", "model", "exit"],
                                ignore_case=True, sentence=True),
        complete_while_typing=True,
        style=Style.from_dict({"prompt": "#2E6DA4 bold"}),
    )
    history: list = []

    while True:
        try:
            user_input = (await session.prompt_async(
                HTML("<prompt>❯ </prompt>"),
                bottom_toolbar=lambda: _toolbar(workspace, model, res["counts"]),
            )).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("[dim]再见。[/]")
            break
        if not user_input:
            continue
        cmd = user_input.lstrip("/").lower()

        if cmd in ("exit", "quit", "q"):
            console.print("[dim]再见。[/]"); break
        if cmd == "clear":
            history = []; console.clear()
            console.print(Panel(BANNER, border_style="#2E6DA4", expand=False))
            continue
        if cmd == "status":
            res = run_status(workspace, grid_path=grid_path, out_dir=out_dir)
            _print_status(res); continue
        if cmd == "report":
            console.print(f"报告：{res['outputs']['status_md']}\n命令：{res['outputs']['next_commands_sh']}")
            continue
        if cmd == "model":
            name = (await session.prompt_async(HTML(f"<prompt>模型（当前 {model}，回车不变）: </prompt>"))).strip()
            if name and name != model:
                model = name
                agent = build_status_agent(workspace, grid_path, out_dir, model=model)
                console.print(f"[green]已切换模型：{model}（记忆保留）[/]")
            continue
        if cmd == "run":
            cmds = _read_commands(out_dir)
            if not cmds:
                console.print("[dim]没有待执行命令。先 /status 生成。[/]"); continue
            if confirm_execution(cmds):
                for c in cmds:
                    console.print(f"[dim]运行：{c}[/]")
                    r = run_command(c, dry_run=False)
                    console.print(f"  returncode={r.get('returncode')}")
            else:
                console.print("[dim]已取消。[/]")
            continue

        history = await _answer(agent, user_input, history)

"""
cli.py
Claude Code 风格的终端界面。

特性：
- 启动 banner（项目名 + 当前模式 + 提示）
- 斜杠命令自动补全：/help /find /viz /matrix /papers /clear /exit + 模板 1-7
- 带边框、可历史回溯（↑↓）的输入框（prompt_toolkit）
- 回答用 Markdown 渲染（rich），思考时显示转圈动画
- 优先流式输出（逐字打印），不支持时自动回退

依赖 rich + prompt_toolkit。任一不可用或非交互终端时，app.py 会回退到简易版。
"""

import asyncio

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live
from rich.text import Text
from rich.spinner import Spinner

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML

from src.agent import ask_agent, ask_agent_stream, build_multi_agent
from src.commands import do_find, do_viz, do_matrix
from src.cache import list_cache
from src.prompts import TEMPLATES

console = Console()

SLASH = {
    "/help": "显示帮助",
    "/find": "联网搜索相关论文 + 研究图景图",
    "/viz": "重新生成研究图景图",
    "/matrix": "生成对比矩阵 + 指标图",
    "/papers": "方向键多选追加论文",
    "/cache": "查看缓存",
    "/clear": "清屏",
    "/exit": "退出",
}

BANNER = """[bold #2E6DA4]Paper Critic Agent[/]  ·  审稿式论文阅读助手

输入问题直接提问，或用 [bold]/[/] 唤出命令（Tab 补全）。
模板 [bold]1-7[/] 一键调用 · [bold]/find[/] 联网搜论文 · [bold]/matrix[/] 对比表 · [bold]/papers[/] 加论文 · [bold]/exit[/] 退出"""


def _completer() -> WordCompleter:
    words = list(SLASH.keys()) + [str(i) for i in range(1, 8)] + ["find ", "viz", "matrix", "exit"]
    return WordCompleter(words, ignore_case=True, sentence=True)


def _toolbar(mode_label: str, retriever):
    n = len(retriever.papers) if (retriever is not None and hasattr(retriever, "papers")) else 1
    return HTML(f" <b>模式</b> {mode_label}  ·  <b>论文</b> {n} 篇  ·  Tab 补全命令  ·  Ctrl-C 退出")


def _print_help():
    lines = "\n".join(f"  [bold]{k}[/]  {v}" for k, v in SLASH.items())
    tpl = "\n".join(f"  [bold]{k}[/]  {v['name']}" for k, v in TEMPLATES.items())
    console.print(Panel(f"{lines}\n\n[dim]预设模板（直接输入编号）[/]\n{tpl}",
                        title="命令", border_style="#2E6DA4", expand=False))


async def _answer(agent, question: str):
    """优先流式渲染；失败回退非流式 + Markdown。"""
    try:
        buf = {"t": ""}
        with Live(console=console, refresh_per_second=12, vertical_overflow="visible") as live:
            live.update(Spinner("dots", text=" 分析中…", style="#2E6DA4"))
            first = {"got": False}

            def on_delta(d: str):
                if not first["got"]:
                    first["got"] = True
                buf["t"] += d
                live.update(Markdown(buf["t"]))

            full = await ask_agent_stream(agent, question, on_delta)
            if not buf["t"]:                      # 没有流出任何增量
                live.update(Markdown(full or "（无内容）"))
        return
    except Exception:
        pass  # 回退

    with console.status(" 分析中…", spinner="dots", spinner_style="#2E6DA4"):
        answer = await ask_agent(agent, question)
    console.print(Markdown(answer))


async def run_cli(agent, mode_label: str, retriever=None, papers_dir: str = "papers"):
    console.print(Panel(BANNER, border_style="#2E6DA4", expand=False))

    session = PromptSession(
        history=InMemoryHistory(),
        completer=_completer(),
        complete_while_typing=True,
        style=Style.from_dict({"prompt": "#2E6DA4 bold"}),
    )

    state: dict = {"last_results": None, "last_query": ""}
    supports_multi = retriever is not None and hasattr(retriever, "add_paper")

    while True:
        try:
            user_input = (await session.prompt_async(
                HTML("<prompt>❯ </prompt>"),
                bottom_toolbar=lambda: _toolbar(mode_label, retriever),
            )).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("[dim]再见。[/]")
            break

        if not user_input:
            continue

        cmd = user_input.lstrip("/").lower()

        if cmd in ("exit", "quit", "q"):
            console.print("[dim]再见。[/]")
            break
        if cmd in ("help", "h"):
            _print_help()
            continue
        if cmd == "clear":
            console.clear()
            console.print(Panel(BANNER, border_style="#2E6DA4", expand=False))
            continue
        if cmd == "cache":
            entries = list_cache()
            if not entries:
                console.print("[dim]缓存为空。[/]")
            else:
                for e in entries:
                    console.print(f"  {e['name']}  ({e['size_kb']:.0f} KB)")
            continue

        # /find <关键词>
        if cmd.startswith("find"):
            query = user_input.split(None, 1)[1].strip() if len(user_input.split(None, 1)) > 1 else ""
            if not query:
                console.print("[dim]用法：/find <主题关键词>[/]")
                continue
            await do_find(query, state, echo=console.print)
            continue

        if cmd == "viz":
            do_viz(state, echo=console.print)
            continue

        if cmd in ("papers",):
            if not supports_multi:
                console.print("[dim]/papers 仅在多论文 / 论文库模式可用。[/]")
                continue
            from src.selector import pick_papers_async
            picked = await pick_papers_async(papers_dir)
            existing = {p["path"] for p in retriever.papers.values()}
            new_paths = [p for p in picked if p not in existing]
            if not new_paths:
                console.print("[dim]没有新增论文。[/]")
                continue
            for p in new_paths:
                retriever.add_paper(p)
            console.print(retriever.paper_list_str())
            agent = build_multi_agent(retriever)
            console.print("[green]已更新：新论文已加入当前会话。[/]")
            continue

        if cmd == "matrix":
            if retriever is None or not hasattr(retriever, "papers"):
                console.print("[dim]matrix 仅在多论文 / 论文库模式可用。[/]")
                continue
            if len(retriever.papers) < 2:
                console.print("[dim]至少需要 2 篇论文才能生成对比矩阵。[/]")
                continue
            await do_matrix(retriever, echo=console.print)
            continue

        # 模板编号
        if user_input in TEMPLATES:
            question = TEMPLATES[user_input]["prompt"]
            console.print(f"[dim]模板：{TEMPLATES[user_input]['name']}[/]")
        else:
            question = user_input

        await _answer(agent, question)

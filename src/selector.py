"""
selector.py
交互式选择论文：方向键移动、空格选中、回车确认（基于 questionary）。

注意：本程序运行在 asyncio 事件循环内，questionary 的同步 .ask() 会报
"asyncio.run() cannot be called from a running event loop"。
因此对外提供 async 版 pick_papers_async（用 .ask_async()），由 async 调用方 await。
保留同步 pick_papers 仅供非事件循环场景，会自动检测并回退。

无 questionary 或非交互终端时，自动回退为"编号输入"模式，保证可用。
"""

import asyncio
import sys
from pathlib import Path


def _list_pdfs(papers_dir: str) -> list[Path]:
    d = Path(papers_dir)
    d.mkdir(parents=True, exist_ok=True)
    return sorted(d.glob("*.pdf"))


def _fallback_pick(pdfs: list[Path]) -> list[str]:
    """无 questionary / 非交互时的编号输入回退。"""
    print("\n可选论文：")
    for i, p in enumerate(pdfs, 1):
        print(f"  {i}. {p.name}")
    raw = input("\n输入要加入的编号（逗号分隔，回车=全选）：").strip()
    if not raw:
        return [str(p) for p in pdfs]
    picked = []
    for tok in raw.replace("，", ",").split(","):
        tok = tok.strip()
        if tok.isdigit() and 1 <= int(tok) <= len(pdfs):
            picked.append(str(pdfs[int(tok) - 1]))
    return picked


def _build_choices(pdfs: list[Path]):
    import questionary
    return [questionary.Choice(title=p.name, value=str(p)) for p in pdfs]


async def pick_papers_async(
    papers_dir: str = "papers",
    message: str = "选择要加入的论文（空格选中，回车确认）：",
) -> list[str]:
    """在 asyncio 事件循环内安全使用：方向键多选，返回选中的 PDF 路径列表。"""
    pdfs = _list_pdfs(papers_dir)
    if not pdfs:
        print(f"[提示] {papers_dir}/ 目录下没有 PDF。请先放入论文，或用 find 命令联网搜索下载。")
        return []

    if not sys.stdin.isatty():
        return _fallback_pick(pdfs)

    try:
        import questionary
        selected = await questionary.checkbox(message, choices=_build_choices(pdfs)).ask_async()
        return selected or []
    except ImportError:
        print("[提示] 未安装 questionary，使用编号选择模式。"
              "（pip install questionary 可启用方向键选择）")
        return _fallback_pick(pdfs)
    except Exception as e:
        print(f"[提示] 交互选择不可用（{e}），回退编号模式。")
        return _fallback_pick(pdfs)


def pick_papers(
    papers_dir: str = "papers",
    message: str = "选择要加入的论文（空格选中，回车确认）：",
) -> list[str]:
    """
    同步入口。若当前已在事件循环内（questionary 同步接口会崩），自动回退编号模式；
    否则用 questionary 方向键多选。
    """
    pdfs = _list_pdfs(papers_dir)
    if not pdfs:
        print(f"[提示] {papers_dir}/ 目录下没有 PDF。请先放入论文，或用 find 命令联网搜索下载。")
        return []

    if not sys.stdin.isatty():
        return _fallback_pick(pdfs)

    # 已在事件循环内 → 同步 questionary 不可用，直接回退
    try:
        asyncio.get_running_loop()
        in_loop = True
    except RuntimeError:
        in_loop = False
    if in_loop:
        return _fallback_pick(pdfs)

    try:
        import questionary
        selected = questionary.checkbox(message, choices=_build_choices(pdfs)).ask()
        return selected or []
    except ImportError:
        return _fallback_pick(pdfs)
    except Exception as e:
        print(f"[提示] 交互选择不可用（{e}），回退编号模式。")
        return _fallback_pick(pdfs)

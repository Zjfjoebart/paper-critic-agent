"""
file_tools.py
扫描研究项目目录结构（Layer 1，纯 Python，只读）。
"""

from pathlib import Path


SUBDIRS = ["configs", "logs", "results", "scripts", "reports"]


def list_project_files(workspace: str) -> dict:
    """
    列出 workspace 下 configs / logs / results / scripts / reports 中的文件。

    Returns:
        {"configs": [...], "logs": [...], "results": [...], ...}（值为相对 workspace 的路径列表）
    """
    ws = Path(workspace)
    out = {}
    for sub in SUBDIRS:
        d = ws / sub
        if d.is_dir():
            out[sub] = sorted(str(p.relative_to(ws)) for p in d.iterdir() if p.is_file() and p.name != ".gitkeep")
        else:
            out[sub] = []
    return out


def summary(workspace: str) -> str:
    files = list_project_files(workspace)
    return "项目文件概览：\n" + "\n".join(
        f"  {sub}/: {len(paths)} 个文件" for sub, paths in files.items()
    )

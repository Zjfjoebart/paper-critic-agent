"""
safety.py
三级权限控制 + 人工确认（设计文档 §13）。
默认只允许 Level 0（只读）和 Level 1（写派生文件）。
Level 2（执行命令）必须人工确认。
"""

LEVELS = {
    0: "只读（list/read configs/logs/results）",
    1: "写派生文件（missing/failed/commands/report）",
    2: "执行命令（训练/评测/批量任务）",
}

DEFAULT_MAX_LEVEL = 1   # Agent 默认能力上限：只读 + 写派生文件


def allowed(level: int, max_level: int = DEFAULT_MAX_LEVEL) -> bool:
    return level <= max_level


def confirm_execution(commands: list[str]) -> bool:
    """Level 2：执行前人工确认。返回 True 表示用户同意。"""
    print(f"\n⚠️ 准备执行 {len(commands)} 条命令（可能占用 GPU）：")
    for c in commands[:10]:
        print(f"    {c}")
    if len(commands) > 10:
        print(f"    … 其余 {len(commands) - 10} 条")
    try:
        ans = input("\n确认执行？只有输入 yes 才会真正运行：").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return ans == "yes"

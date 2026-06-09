"""
log_tools.py
解析训练/评测日志，识别失败原因（Layer 1，纯 Python，正则匹配）。
"""

import re
from pathlib import Path

# 错误类型 -> 匹配模式（按优先级从上到下）
ERROR_PATTERNS = [
    ("CUDA_OOM",        re.compile(r"CUDA out of memory|OutOfMemoryError", re.I)),
    ("FileNotFound",    re.compile(r"FileNotFoundError|No such file or directory|not found", re.I)),
    ("NaNLoss",         re.compile(r"\bnan\b.*loss|loss\s*=\s*nan|NaN loss", re.I)),
    ("EarlyStopped",    re.compile(r"early stopped", re.I)),
    ("AssertionError",  re.compile(r"AssertionError", re.I)),
    ("KeyError",        re.compile(r"KeyError", re.I)),
    ("RuntimeError",    re.compile(r"RuntimeError", re.I)),
]

FINISHED_RE = re.compile(r"evaluation finished|training finished|done\.", re.I)
METRIC_MISSING_RE = re.compile(r"result dump missing|metric missing|missing accuracy", re.I)


def parse_log(log_path: str) -> dict:
    """
    解析单个日志文件。

    Returns:
        {"finished": bool, "error_type": str|None, "metric_missing": bool, "evidence": str}
    """
    text = Path(log_path).read_text(encoding="utf-8", errors="ignore")
    finished = bool(FINISHED_RE.search(text))
    metric_missing = bool(METRIC_MISSING_RE.search(text))

    error_type, evidence = None, ""
    for name, pat in ERROR_PATTERNS:
        m = pat.search(text)
        if m:
            error_type = name
            # 取命中行作为证据
            line = next((ln.strip() for ln in text.splitlines() if pat.search(ln)), m.group(0))
            evidence = line[:200]
            break

    return {
        "finished": finished,
        "error_type": error_type,
        "metric_missing": metric_missing,
        "evidence": evidence,
    }

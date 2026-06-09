"""
main_agent.py
第 2 层：接入 LLM（DeepSeek，OpenAI 兼容）的 ResearchOps Agent。
LLM 只做解释/判断/建议；所有确定性计算通过工具调用 pipeline 完成。
"""

import os
import json

from openai import AsyncOpenAI
from agents import (Agent, Runner, function_tool,
                    set_default_openai_client, set_default_openai_api, set_tracing_disabled)

from agent.pipeline import run_status
from agent.state import build_ledger
from agent.tools.config_tools import load_grid
from agent.prompts import SYSTEM_PROMPT


def _setup_deepseek():
    client = AsyncOpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )
    set_default_openai_client(client)
    set_default_openai_api("chat_completions")
    set_tracing_disabled(True)


def build_status_agent(workspace: str, grid_path: str | None = None,
                       out_dir: str = "outputs", model: str | None = None) -> Agent:
    """构建 ResearchOps Agent。工具捕获 workspace 上下文。"""
    _setup_deepseek()
    model = model or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

    @function_tool
    def experiment_status() -> str:
        """获取当前项目的实验状态：完成度、失败原因分布、异常结果、结果汇总表。"""
        res = run_status(workspace, grid_path=grid_path, out_dir=out_dir)
        # 只回传确定性事实，交给 LLM 解释
        payload = {
            "total": res["total"],
            "counts": res["counts"],
            "failed_breakdown": res["failed_breakdown"],
            "anomalies": res["anomalies"],
            "summary_rows": res["summary_rows"],
            "missing_count": len(res["missing"]),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @function_tool
    def failed_details() -> str:
        """列出失败实验及其日志证据（错误类型 + 命中的日志行），供解释失败原因。"""
        from agent.tools.log_tools import parse_log
        ledger = build_ledger(workspace, grid_path or f"{workspace}/grid.yaml")
        out = []
        for e in ledger:
            if e.status == "failed":
                ev = parse_log(e.log_path) if e.log_path else {}
                out.append({"run_id": e.run_id, "error_type": e.error_type,
                            "evidence": ev.get("evidence", ""), "model": e.model, "task": e.task})
        return json.dumps(out, ensure_ascii=False, indent=2) if out else "无失败实验。"

    @function_tool
    def next_commands() -> str:
        """获取为缺失实验生成的下一批命令（仅生成，不执行）。"""
        res = run_status(workspace, grid_path=grid_path, out_dir=out_dir)
        path = res["outputs"]["next_commands_sh"]
        try:
            return open(path, encoding="utf-8").read()
        except Exception:
            return "（暂无）"

    return Agent(
        name="ResearchOps Agent",
        model=model,
        instructions=SYSTEM_PROMPT,
        tools=[experiment_status, failed_details, next_commands],
    )


async def ask_agent(agent: Agent, question: str, history: list | None = None):
    """带多轮记忆地提问。返回 (answer, new_history)。"""
    input_list = (history or []) + [{"role": "user", "content": question}]
    result = await Runner.run(agent, input_list)
    return result.final_output, result.to_input_list()


async def ask_agent_stream(agent: Agent, question: str, on_delta, history: list | None = None):
    """流式提问。返回 (text, new_history)。失败由调用方回退。"""
    from openai.types.responses import ResponseTextDeltaEvent
    input_list = (history or []) + [{"role": "user", "content": question}]
    result = Runner.run_streamed(agent, input_list)
    pieces = []
    async for event in result.stream_events():
        if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
            d = event.data.delta or ""
            if d:
                pieces.append(d)
                on_delta(d)
    return "".join(pieces) or (result.final_output or ""), result.to_input_list()

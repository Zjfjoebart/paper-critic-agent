"""
agent.py
核心 Agent：使用 OpenAI Agents SDK + DeepSeek API。

单论文模式：工具 search_paper + keyword_search
多论文模式：工具 search_all_papers + search_one_paper + compare_papers + keyword_search
"""

import os
from openai import AsyncOpenAI
from agents import Agent, Runner, function_tool, set_default_openai_client, set_default_openai_api, set_tracing_disabled

from src.retriever import PaperRetriever
from src.multi_retriever import MultiPaperRetriever
from src.prompts import SYSTEM_PROMPT, MULTI_PAPER_SYSTEM_PROMPT
from src.paper_finder import find_papers, format_results as format_found


def _setup_deepseek():
    """初始化 DeepSeek 客户端（幂等）。"""
    deepseek_client = AsyncOpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )
    set_default_openai_client(deepseek_client)
    set_default_openai_api("chat_completions")
    set_tracing_disabled(True)


# ====================================================================== #
#  单论文 Agent
# ====================================================================== #

def build_agent(retriever: PaperRetriever) -> Agent:
    """单论文模式 Agent。"""
    _setup_deepseek()

    @function_tool
    def search_paper(query: str) -> str:
        """
        语义检索论文中与问题最相关的原文段落。
        使用场景：找与某个概念、方法、实验相关的内容。
        """
        results = retriever.hybrid_search(query, top_k=5)
        if not results:
            return "未找到相关内容。"
        parts = [
            f"[p.{r['page']} | 相关度={r['score']:.3f}]\n{r['text']}"
            for r in results
        ]
        return "\n\n---\n\n".join(parts)

    @function_tool
    def keyword_search(keyword: str) -> str:
        """
        关键词精确匹配，找包含特定术语的段落。
        使用场景：查找具体数字、模型名、数据集名、方法名。
        """
        results = retriever.keyword_search(keyword, top_k=5)
        if not results:
            return f"论文中未找到包含关键词 '{keyword}' 的段落。"
        parts = [
            f"[p.{r['page']}]\n{r['text']}"
            for r in results
        ]
        return "\n\n---\n\n".join(parts)

    @function_tool
    def find_related_papers(query: str) -> str:
        """
        联网搜索与某主题相关的论文（Semantic Scholar），返回标题/作者/年份/会议/引用数。
        使用场景：用户问"这个方向还有哪些相关工作/顶会论文""谁的引用最高"。
        query 用英文主题词效果最好。
        """
        try:
            results = find_papers(query, limit=12)
        except Exception as e:
            return f"联网搜索失败：{e}"
        return format_found(results)

    return Agent(
        name="Paper Critic Agent",
        model="deepseek-chat",
        instructions=SYSTEM_PROMPT,
        tools=[search_paper, keyword_search, find_related_papers],
    )


# ====================================================================== #
#  多论文 Agent
# ====================================================================== #

def build_multi_agent(retriever: MultiPaperRetriever) -> Agent:
    """
    多论文模式 Agent。
    多出 search_one_paper、compare_papers 两个工具。
    """
    _setup_deepseek()

    paper_list = retriever.paper_list_str()

    @function_tool
    def search_all_papers(query: str) -> str:
        """
        跨所有论文语义检索，结果标注来源论文和页码。
        使用场景：在多篇论文中同时找相关段落。
        """
        results = retriever.hybrid_search(query, top_k=6)
        return retriever.format_results(results)

    @function_tool
    def search_one_paper(paper_name: str, query: str) -> str:
        """
        在指定论文中检索。paper_name 是论文的文件名（不含 .pdf）。
        使用场景：想聚焦某篇论文内部的证据。
        """
        # 匹配 paper_id
        target_id = None
        for pid, info in retriever.papers.items():
            if paper_name.lower() in info["name"].lower():
                target_id = pid
                break

        if target_id is None:
            return f"未找到名为 '{paper_name}' 的论文。已加载论文：\n{paper_list}"

        results = retriever.hybrid_search(query, top_k=5, paper_id=target_id)
        return retriever.format_results(results)

    @function_tool
    def compare_papers(aspect: str) -> str:
        """
        对比所有论文在某个维度（aspect）的相关内容。
        自动为每篇论文单独检索，结果按论文分组展示。
        使用场景：对比"方法创新点"、"实验结果"、"局限性"等横向维度。
        """
        per_paper = retriever.search_per_paper(aspect, top_k_per_paper=3)
        sections = []
        for pid, results in per_paper.items():
            name = retriever.papers[pid]["name"]
            evidence = retriever.format_results(results)
            sections.append(f"=== {name} ===\n{evidence}")
        return "\n\n".join(sections)

    @function_tool
    def recommend_directions(focus: str = "") -> str:
        """
        汇总所有论文中"局限 / 未来工作 / 缺失 baseline / 未覆盖场景"的原文证据，
        为"研究切入点推荐"提供集中素材（按论文分组返回）。
        focus 可选：聚焦某个子方向（如"长上下文""推理效率"），留空则全局汇总。
        使用场景：模板 7 / 用户问"还能往哪个方向做"。
        """
        queries = [
            "limitation weakness shortcoming",
            "future work remaining challenge open problem",
            "does not handle fails when not applicable scenario",
            "missing baseline comparison not evaluated",
        ]
        if focus.strip():
            queries.append(focus.strip())

        sections = []
        for pid, info in retriever.papers.items():
            name = info["name"]
            seen = set()
            evid = []
            for q in queries:
                for r in retriever.hybrid_search(q, top_k=2, paper_id=pid):
                    key = (r["page"], r["text"][:60])
                    if key not in seen:
                        seen.add(key)
                        evid.append(f"[p.{r['page']}] {r['text']}")
            body = "\n\n".join(evid) if evid else "（未检索到明确的局限/未来工作段落）"
            sections.append(f"=== {name} ===\n{body}")
        return "\n\n".join(sections)

    @function_tool
    def keyword_search(keyword: str) -> str:
        """
        跨所有论文关键词精确匹配。
        使用场景：查找特定术语、数字、模型名在各论文中的出现位置。
        """
        results = retriever.keyword_search(keyword, top_k=6)
        return retriever.format_results(results)

    @function_tool
    def find_related_papers(query: str) -> str:
        """
        联网搜索与某主题相关的论文（Semantic Scholar），返回标题/作者/年份/会议/引用数。
        使用场景：在对比/综述时补充库外的相关顶会工作。query 用英文主题词效果最好。
        """
        try:
            results = find_papers(query, limit=12)
        except Exception as e:
            return f"联网搜索失败：{e}"
        return format_found(results)

    system = MULTI_PAPER_SYSTEM_PROMPT.format(paper_list=paper_list)

    return Agent(
        name="Multi-Paper Critic Agent",
        model="deepseek-chat",
        instructions=system,
        tools=[search_all_papers, search_one_paper, compare_papers, recommend_directions, keyword_search, find_related_papers],
    )


# ====================================================================== #
#  通用入口
# ====================================================================== #

async def ask_agent(agent: Agent, question: str) -> str:
    """向 Agent 提问，返回最终回答。"""
    result = await Runner.run(agent, question)
    return result.final_output


async def ask_agent_stream(agent: Agent, question: str, on_delta) -> str:
    """
    流式提问：每个文本增量调用 on_delta(text)，返回完整回答。
    若底层 SDK 不支持流式，调用方应捕获异常并回退到 ask_agent。
    """
    from openai.types.responses import ResponseTextDeltaEvent

    result = Runner.run_streamed(agent, question)
    pieces: list[str] = []
    async for event in result.stream_events():
        if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
            delta = event.data.delta or ""
            if delta:
                pieces.append(delta)
                on_delta(delta)
    return "".join(pieces) or (result.final_output or "")

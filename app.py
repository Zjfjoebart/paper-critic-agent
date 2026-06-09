"""
app.py
Paper Critic Agent — CLI 入口。

用法：
    # 交互式启动：方向键多选 papers/ 里的论文（空格选中，回车确认）
    python app.py

    # 单论文 / 多论文
    python app.py papers/A.pdf
    python app.py papers/A.pdf papers/B.pdf papers/C.pdf

    # 联网搜索相关论文（Semantic Scholar，带会议/年份/引用数）
    python app.py --find "token pruning vision language model"

    # 从 arXiv 检索并下载论文到 papers/
    python app.py --arxiv "token pruning vlm" --download all

    # 论文库模式（索引 papers/ 目录，持久化、增量更新）
    python app.py --library
    python app.py --library mypapers/      # 指定目录
    python app.py --library --rebuild      # 忽略旧索引重建

    # 管理缓存
    python app.py --cache-list
    python app.py --cache-clear

交互中命令：1-7 模板、find <关键词>、viz、matrix、/papers、cache、help、exit
"""

import asyncio
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from src.parse_pdf import parse_pdf
from src.chunker import chunk_pages
from src.retriever import PaperRetriever
from src.multi_retriever import MultiPaperRetriever
from src.agent import build_agent, build_multi_agent, ask_agent
from src.cache import list_cache, clear_cache
from src.prompts import TEMPLATES, TEMPLATE_MENU
from src.commands import do_find, do_viz, do_matrix, VIZ_DIR
from src.config import get_chat_model, AVAILABLE_MODELS


# ====================================================================== #
#  启动检查
# ====================================================================== #

def check_env():
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("[错误] 未找到 DEEPSEEK_API_KEY。")
        print("请在项目根目录创建 .env 文件，内容：DEEPSEEK_API_KEY=sk-xxx")
        sys.exit(1)


def validate_pdf(path_str: str) -> Path:
    path = Path(path_str)
    if not path.exists():
        print(f"[错误] 文件不存在：{path_str}")
        sys.exit(1)
    if path.suffix.lower() != ".pdf":
        print(f"[错误] 请提供 PDF 文件：{path_str}")
        sys.exit(1)
    return path


def handle_cli_flags(args: list[str]) -> bool:
    """处理非交互式 CLI flags，返回 True 表示已处理（程序可退出）。"""
    if "--arxiv" in args:
        from src.arxiv_search import _main as arxiv_main
        rest = [a for a in args if a != "--arxiv"]
        arxiv_main(rest)
        return True

    if "--find" in args:
        from src.paper_finder import find_papers, format_results
        from src.visualize import viz_landscape
        rest = [a for a in args if a != "--find" and not a.startswith("--")]
        query = " ".join(rest)
        if not query:
            print('用法：python app.py --find "主题关键词"')
            return True
        print(f"联网搜索：{query}\n")
        try:
            results = find_papers(query, limit=15)
        except Exception as e:
            print(f"[错误] 搜索失败：{e}")
            return True
        print(format_results(results))
        if results:
            html = viz_landscape(results, out_dir=VIZ_DIR, query=query)
            print(f"\n研究图景已生成：{html}（用浏览器打开）")
        return True

    if "--cache-list" in args:
        entries = list_cache()
        if not entries:
            print("缓存为空。")
        else:
            print(f"共 {len(entries)} 个缓存文件：")
            for e in entries:
                print(f"  {e['name']}  ({e['size_kb']:.0f} KB)")
        return True

    if "--cache-clear" in args:
        n = clear_cache()
        print(f"已删除 {n} 个缓存文件。")
        return True

    return False


# ====================================================================== #
#  论文加载
# ====================================================================== #

def load_single_paper(pdf_path: str) -> PaperRetriever:
    path = validate_pdf(pdf_path)
    print(f"\n正在加载：{path.name}")
    pages = parse_pdf(str(path))
    chunks = chunk_pages(pages)
    print(f"解析完成，共 {len(pages)} 页，{len(chunks)} 块")
    return PaperRetriever(chunks, pdf_path=str(path))


def load_multi_papers(pdf_paths: list[str]) -> MultiPaperRetriever:
    for p in pdf_paths:
        validate_pdf(p)
    retriever = MultiPaperRetriever()
    for p in pdf_paths:
        retriever.add_paper(p)
    print(f"\n{retriever.paper_list_str()}")
    return retriever


# ====================================================================== #
#  交互命令辅助
# ====================================================================== #

HELP_TEXT = """
命令速查：
  1-7            使用预设模板（7=研究切入点推荐）
  find <关键词>  联网搜索相关论文（带会议/年份/引用数）+ 生成研究图景图
  viz            重新生成上次搜索结果的研究图景图
  matrix         生成 Literature Matrix（多论文/论文库模式）+ 指标对比图
  /papers        方向键多选，往会话里追加 papers/ 目录的论文
  cache          查看当前缓存状态
  help / h       显示此帮助
  exit / q       退出
"""


# ====================================================================== #
#  主循环
# ====================================================================== #

async def chat_loop(agent, mode_label: str, retriever=None, papers_dir: str = "papers",
                    agent_builder=None, model: str | None = None):
    print("\n" + "=" * 55)
    print(f"Paper Critic Agent [{mode_label}]")
    print("=" * 55)
    print(TEMPLATE_MENU)

    state: dict = {"last_results": None, "last_query": ""}
    history: list = []
    model = model or get_chat_model()
    supports_multi = isinstance(retriever, MultiPaperRetriever)

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break

        if not user_input:
            continue

        low = user_input.lower()

        if low in ["exit", "quit", "q"]:
            print("再见。")
            break

        if low in ["help", "h"]:
            print(HELP_TEXT)
            print(TEMPLATE_MENU)
            continue

        if low == "cache":
            entries = list_cache()
            if not entries:
                print("缓存为空。")
            else:
                for e in entries:
                    print(f"  {e['name']}  ({e['size_kb']:.0f} KB)")
            continue

        if low in ["clear", "/clear"]:
            history = []
            print("对话记忆已清空。")
            continue

        # 切换模型（仅精确输入 model / /model 触发，避免和正常提问冲突）
        if low in ["model", "/model"]:
            if agent_builder is None:
                print("[提示] 当前模式不支持切换模型。")
                continue
            print(f"当前模型：{model}。可选：{', '.join(AVAILABLE_MODELS)}")
            name = input("输入要切换的模型名（回车保持不变）：").strip()
            if not name or name == model:
                print("模型未变。")
                continue
            model = name
            agent = agent_builder(model)
            print(f"已切换模型：{model}（对话记忆保留）")
            continue

        # 联网搜索相关论文
        if low.startswith("find ") or low == "find":
            query = user_input[4:].strip() if len(user_input) > 4 else ""
            if not query:
                print("用法：find <主题关键词>，例如 find token pruning vlm")
                continue
            await do_find(query, state)
            continue

        if low == "viz":
            do_viz(state)
            continue

        # 方向键多选追加论文
        if low in ["/papers", "papers"]:
            if not supports_multi:
                print("[提示] /papers 仅在多论文 / 论文库模式可用。"
                      "无参启动（python app.py）或加 --library 即可。")
                continue
            from src.selector import pick_papers_async
            picked = await pick_papers_async(papers_dir)
            existing = {p["path"] for p in retriever.papers.values()}
            new_paths = [p for p in picked if p not in existing]
            if not new_paths:
                print("没有新增论文。")
                continue
            for p in new_paths:
                retriever.add_paper(p)
            print(f"\n{retriever.paper_list_str()}")
            agent = build_multi_agent(retriever)  # 重建 agent，纳入新论文
            print("[已更新] 新论文已加入当前会话。")
            continue

        # Literature Matrix（仅多论文 / 论文库模式）
        if low == "matrix":
            if retriever is None or not hasattr(retriever, "papers"):
                print("[提示] matrix 命令仅在多论文 / 论文库模式下可用。")
                continue
            if len(retriever.papers) < 2:
                print("[提示] 至少需要加载 2 篇论文才能生成对比矩阵。")
                continue
            await do_matrix(retriever)
            continue

        # 预设模板快捷键
        if user_input in TEMPLATES:
            question = TEMPLATES[user_input]["prompt"]
            print(f"\n[模板：{TEMPLATES[user_input]['name']}]")
        else:
            question = user_input

        print("\n正在分析，请稍候...\n")
        try:
            answer, history = await ask_agent(agent, question, history)
            print("=" * 55)
            print(answer)
            print("=" * 55)
        except Exception as e:
            print(f"[错误] {type(e).__name__}: {e}")


# ====================================================================== #
#  界面选择：默认 Claude Code 风格富 CLI，--plain 或环境不支持时回退简易版
# ====================================================================== #

async def launch(agent, mode_label: str, retriever=None, papers_dir: str = "papers",
                 agent_builder=None, model: str | None = None):
    if "--plain" not in sys.argv and sys.stdin.isatty():
        try:
            from src.cli import run_cli
            await run_cli(agent, mode_label, retriever=retriever, papers_dir=papers_dir,
                          agent_builder=agent_builder, model=model)
            return
        except ImportError:
            print("[提示] 未安装 rich / prompt_toolkit，使用简易界面。"
                  "（pip install rich prompt_toolkit 可启用 Claude Code 风格界面）")
    await chat_loop(agent, mode_label, retriever=retriever, papers_dir=papers_dir,
                    agent_builder=agent_builder, model=model)


# ====================================================================== #
#  入口
# ====================================================================== #

async def main():
    args = sys.argv[1:]

    if handle_cli_flags(args):
        return

    check_env()

    # 论文库模式
    if "--library" in args or "--lib" in args:
        from src.library import build_or_load_library
        rebuild = "--rebuild" in args
        positional = [a for a in args if not a.startswith("--")]
        papers_dir = positional[0] if positional else "papers"
        lib = build_or_load_library(papers_dir, rebuild=rebuild)
        if not lib.papers:
            print(f"[提示] {papers_dir} 目录下没有可索引的 PDF。请放入论文后重试。")
            return
        print(f"\n{lib.paper_list_str()}")
        model = get_chat_model()
        builder = lambda m=None: build_multi_agent(lib, m)
        agent = builder(model)
        await launch(agent, mode_label=f"论文库×{len(lib.papers)}",
                     retriever=lib, papers_dir=papers_dir,
                     agent_builder=builder, model=model)
        return

    pdf_paths = [a for a in args if not a.startswith("--")]

    # 无参 → 方向键多选 papers/ 里的论文
    if not pdf_paths:
        from src.selector import pick_papers_async
        pdf_paths = await pick_papers_async("papers")
        if not pdf_paths:
            print("[提示] 未选择任何论文。可先把 PDF 放进 papers/，"
                  '或用 python app.py --find "关键词" 联网搜索。')
            return

    if len(pdf_paths) == 1:
        retriever = load_single_paper(pdf_paths[0])
        model = get_chat_model()
        builder = lambda m=None: build_agent(retriever, m)
        agent = builder(model)
        await launch(agent, mode_label="单论文",
                     agent_builder=builder, model=model)
    else:
        print(f"\n检测到 {len(pdf_paths)} 篇论文，进入多论文对比模式。")
        retriever = load_multi_papers(pdf_paths)
        model = get_chat_model()
        builder = lambda m=None: build_multi_agent(retriever, m)
        agent = builder(model)
        await launch(agent, mode_label=f"多论文×{len(pdf_paths)}",
                     retriever=retriever, papers_dir="papers",
                     agent_builder=builder, model=model)


if __name__ == "__main__":
    asyncio.run(main())

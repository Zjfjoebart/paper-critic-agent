# Paper Critic Agent

审稿式论文阅读助手。不是 PDF 总结器，而是帮你做研究判断的工具。

当前版本 **v0.8**：支持单论文 / 多论文对比 / 本地论文库，能生成 Literature Matrix、
推荐研究切入点，并可从 arXiv 直接检索下载论文。

默认进入 **Claude Code 风格的终端界面**：斜杠命令自动补全（Tab）、带边框输入框、命令历史（↑↓）、Markdown 渲染回答、思考动画与流式输出、**多轮对话记忆**（支持追问）、**`/model` 随时切换推理模型**。加 `--plain` 可切回简易界面。

---

## 快速开始

### 1. 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> 扫描版 PDF 的 OCR 为可选功能，需在系统层安装 Tesseract：
> `brew install tesseract tesseract-lang`（macOS）或
> `sudo apt install tesseract-ocr tesseract-ocr-chi-sim`（Ubuntu）。
> 不装也能正常运行，只是会跳过扫描页。

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入 DeepSeek API Key
```

DeepSeek API Key 申请：https://platform.deepseek.com

### 3. 运行

```bash
# 单论文
python app.py papers/your_paper.pdf

# 多论文对比
python app.py papers/A.pdf papers/B.pdf papers/C.pdf

# 论文库模式（索引 papers/ 整个目录，持久化 + 增量更新）
python app.py --library

# 无参启动：方向键多选 papers/ 里的论文（空格选、回车确认）
python app.py

# 联网搜索相关顶会论文（带会议/年份/引用数 + 自动出研究图景图）
python app.py --find "token pruning vision language model"
```

---

## 三种使用模式

| 模式 | 命令 | 适用场景 |
|------|------|----------|
| 单论文 | `python app.py a.pdf` | 精读一篇 |
| 多论文 | `python app.py a.pdf b.pdf` | 当场对比几篇 |
| 论文库 | `python app.py --library` | 管理整个文献库，持久化、可增量 |

### 预设模板（启动后输入编号）

| 编号 | 模板 | 模式 |
|------|------|------|
| 1 | 快速审稿（全文结构分析）| 全部 |
| 2 | 方法拆解 | 全部 |
| 3 | 审稿人挑战 | 全部 |
| 4 | 对我研究的价值分析 | 全部 |
| 5 | Related Work 梳理 | 全部 |
| 6 | 多论文横向对比 | 多论文 / 论文库 |
| 7 | **研究切入点推荐** | 多论文 / 论文库 |

也可以直接提问，例如：
- `这篇论文的核心贡献是什么？`
- `实验有没有支撑作者的 claim？`
- `和 SparseVLM 相比有什么区别？`
- `如果我要在这个方向继续做，有哪些可攻击点？`

交互中可用命令：`find <关键词>`（联网搜索 + 研究图景图）、`viz`（重出图景图）、`matrix`（对比表 + 指标对比图）、`/papers`（方向键追加论文）、`/model`（切换 deepseek-chat / deepseek-reasoner）、`/clear`（清空对话记忆）、`cache`、`help`、`exit`。

---

## 论文库工作流

```bash
# 1. 从 arXiv 检索并下载相关论文到 papers/
python app.py --arxiv "token pruning vision language model" --download all

# 2. 索引论文库（首次会 embedding，之后增量；换新论文只索引新增的）
python app.py --library

# 3. 在交互中：用模板 6 横向对比、模板 7 找研究切入点、matrix 生成对比表
```

也可单独使用 arXiv 工具：

```bash
python -m src.arxiv_search "kv cache compression" --max 5
python -m src.arxiv_search "long context attention" --download 1,3,4
```

---

## 一键启动（paper-zjf）

不想每次都 cd / 激活环境 / python app.py？装一次全局命令：

```bash
# 1. 给脚本可执行权限
chmod +x "/Users/zhangjunfeng/Desktop/项目/文献阅读器/paper-zjf"

# 2. 加一个别名到 zsh 配置（只需一次）
echo 'alias paper-zjf="/Users/zhangjunfeng/Desktop/项目/文献阅读器/paper-zjf"' >> ~/.zshrc
source ~/.zshrc
```

之后在任意目录直接输入即可：

```bash
paper-zjf                 # 方向键选论文，进入交互
paper-zjf --library       # 论文库模式
paper-zjf --find "xxx"    # 联网搜索
```

> 项目若移动了位置，编辑 `paper-zjf` 顶部的 `PROJECT_DIR` 即可。

---

## 项目结构

```
文献阅读器/
├── app.py                   # CLI 入口（单/多/库/arXiv/缓存）
├── requirements.txt
├── .env.example
├── papers/                  # 放 PDF 文件
├── data/
│   ├── cache/               # 单 PDF embedding 缓存
│   └── index/               # 论文库持久化 FAISS 索引 + 元数据
└── src/
    ├── config.py            # embedding 模型配置
    ├── parse_pdf.py         # PDF 解析 + 扫描版 OCR 兜底
    ├── chunker.py           # 文本滑动窗口切分
    ├── cache.py             # embedding 缓存（key 含模型名）
    ├── retriever.py         # 单论文检索
    ├── multi_retriever.py   # 多论文检索
    ├── library.py           # 本地论文库索引（持久化 + 增量）
    ├── agent.py             # Agent 主逻辑（OpenAI Agents SDK + DeepSeek）
    ├── arxiv_search.py      # arXiv 检索与下载
    ├── paper_finder.py      # 联网搜相关论文（Semantic Scholar）
    ├── selector.py          # 方向键多选论文
    ├── visualize.py         # 交互式 HTML 图表
    ├── cli.py               # Claude Code 风格终端界面（rich + prompt_toolkit）
    ├── commands.py          # find/viz/matrix 共享命令逻辑
    ├── matrix_builder.py    # Literature Matrix 生成
    └── prompts.py           # 系统提示词 + 7 个模板
```

---

## 技术栈

- **PDF 解析**：PyMuPDF（扫描版 OCR 兜底需 Tesseract）
- **Embedding**：`paraphrase-multilingual-MiniLM-L12-v2`（默认，中英文通用，本地运行）
  - 环境变量 `EMBEDDING_MODEL` 可切换模型
- **向量索引**：FAISS（IndexFlatIP，cosine 相似度，论文库索引持久化）
- **检索策略**：语义检索 + 关键词匹配混合
- **Agent 框架**：OpenAI Agents SDK
- **推理模型**：DeepSeek（`deepseek-chat`）
- **arXiv 检索**：Python 标准库，无额外依赖

---

## 后续升级方向

- [ ] Streamlit 网页界面（上传 / 选模板 / 带引用回答）
- [ ] 引用可点击 / 证据回溯

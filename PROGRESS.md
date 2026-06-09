# Paper Critic Agent — 开发进度文档

## 项目定位

**审稿式论文阅读助手**（Research Paper Critic Agent）

目标：不是 PDF 总结器，而是帮助研究者做研究判断的工具。
- 定位原文证据，拆解方法，质疑实验设计，整理 related work
- 所有回答强制引用页码，不允许编造

---

## 当前版本：v0.8

### 模块总览

| 文件 | 功能 | 状态 |
|------|------|------|
| `src/parse_pdf.py` | PDF 按页解析（PyMuPDF）+ 扫描版 OCR 兜底 | ✅ |
| `src/chunker.py` | 滑动窗口切分，句子边界断开，保留页码 | ✅ |
| `src/cache.py` | 单 PDF embedding 缓存（cache key 含模型名） | ✅ |
| `src/config.py` | embedding 模型集中配置（默认多语言，支持中文） | ✅ |
| `src/retriever.py` | 单论文 FAISS 向量 + 关键词混合检索 | ✅ |
| `src/multi_retriever.py` | 多论文检索器，逐篇缓存 | ✅ |
| `src/library.py` | **本地论文库索引：整库持久化 + 增量更新** | ✅ |
| `src/agent.py` | Agent（OpenAI Agents SDK + DeepSeek），单/多/库三套工具 | ✅ |
| `src/arxiv_search.py` | **arXiv 检索与下载，填充 papers/** | ✅ |
| `src/matrix_builder.py` | Literature Matrix 生成（MD + CSV） | ✅ |
| `src/prompts.py` | 系统提示词 + 7 个审稿/研究模板 | ✅ |
| `src/paper_finder.py` | **联网搜相关论文（Semantic Scholar，带会议/引用数）** | ✅ |
| `src/selector.py` | **方向键多选论文（/papers）** | ✅ |
| `src/visualize.py` | **交互式 HTML 图表（研究图景 + 指标对比）** | ✅ |
| `paper-zjf` | **全局启动命令（任意目录直接启动）** | ✅ |
| `src/cli.py` | **Claude Code 风格终端界面（rich + prompt_toolkit）** | ✅ |
| `src/commands.py` | find/viz/matrix 共享命令逻辑 | ✅ |
| `app.py` | CLI 入口：单论文 / 多论文 / 论文库 / arXiv / 缓存管理 | ✅ |

### 预设模板（输入编号快速调用）

1. 快速审稿（全文结构分析）
2. 方法拆解
3. 审稿人挑战（严苛审稿人视角）
4. 对我研究的价值分析
5. Related Work 梳理
6. 多论文横向对比（多论文 / 论文库模式）
7. **研究切入点推荐**（多论文 / 论文库模式）

### 技术选型

- PDF 解析：PyMuPDF；扫描版自动 OCR 兜底（需系统装 Tesseract）
- Embedding：默认 `paraphrase-multilingual-MiniLM-L12-v2`（384 维，中英文通用，本地运行）
  - 可通过环境变量 `EMBEDDING_MODEL` 切换（如纯英文场景用 `all-MiniLM-L6-v2` 更快）
- 向量索引：FAISS IndexFlatIP（cosine 相似度），论文库索引持久化到 `data/index/`
- 检索策略：语义检索 + 关键词精确匹配，混合去重
- Agent 框架：OpenAI Agents SDK（自定义 base_url）
- 推理模型：DeepSeek（`deepseek-chat`，OpenAI 兼容接口）
- arXiv 检索：Python 标准库（urllib + xml），无额外依赖

---

## 本轮（→ v0.5）完成的工作

### 1. 项目结构整理
- 原本 `app.py` 与 `src/` 分处两个目录，`python app.py` 会 `ModuleNotFoundError`。
- 已合并为顶层单一可运行项目：`app.py` 与 `src/` 同级。

### 2. 本地论文库索引（v0.4）— `src/library.py`
- 扫描 `papers/` 目录下所有 PDF。
- 整库 FAISS 索引持久化到 `data/index/library.faiss`，元数据到 `library.json`。
- **增量更新**：按文件内容哈希判断，已索引且未变的 PDF 直接跳过，只对新增/改动的做 embedding。
- 启动时自动加载已有索引；换 embedding 模型会自动失效重建。
- 检索接口与 `MultiPaperRetriever` 完全对齐，直接接入多论文 Agent。

### 3. 研究切入点推荐（v0.5）— 模板 7 + `recommend_directions` 工具
- 新增工具自动汇总各论文"局限 / 未来工作 / 缺失 baseline / 未覆盖场景"的原文证据。
- 模板 7 强制四段式输出：**问题 → 现有方法不足 → 可攻击点 → 建议实验设计**，并要求引用论文名 + 页码。

### 4. 修复已知短板
- **中文支持**：默认 embedding 模型换为多语言版；并把模型名写进 cache key，
  彻底避免"切换模型后复用旧向量"的脏缓存问题。
- **arXiv 检索/下载**：`src/arxiv_search.py`，命令行直接搜索并下载 PDF 到 `papers/`。
- **扫描版 OCR 兜底**：`parse_pdf` 检测无文字层页面并尝试 OCR；未装 Tesseract 时仅提示、不崩溃。

### 5. 修复一处会导致死循环的 Bug（chunker）
- 旧 `chunker.py` 在"末尾窗口长度 ≤ overlap"时 `start` 不再前进，
  会无限追加同一 chunk 直至进程被 OOM 杀死（真实 PDF 上可触发）。
- 已改为：覆盖到页尾即结束、每轮至少前进 1 个字符。

---

## 本轮（→ v0.6）新增

### 1. 联网搜索相关论文 — `src/paper_finder.py`
- 基于 Semantic Scholar Graph API（免费、无需 key），返回标题/作者/年份/发表会议/引用数。
- 自动标注顶会/顶刊（NeurIPS、ICML、CVPR、ACL 等），按引用数排序。
- 双入口：CLI `find <关键词>` 命令 + Agent 工具 `find_related_papers`（分析时模型可自己联网搜）。

### 2. 方向键多选论文 — `src/selector.py`
- 基于 questionary：方向键移动、空格选中、回车确认。
- 无参启动（`python app.py`）自动弹出选择器；会话中 `/papers` 可随时追加论文并热重建 Agent。
- 非交互终端自动回退为编号输入，保证可用。

### 3. 数据可视化 — `src/visualize.py`
- **研究图景**：搜索结果按 年份 × 引用数 画气泡散点，顶会高亮，悬停看标题/会议；`find` 后自动生成。
- **指标对比**：从 Literature Matrix 数字字段提取数值，做论文间对比柱状图；`matrix` 后自动生成。
- 输出为 Chart.js 交互式 HTML，浏览器直接打开。

### 4. 全局启动命令 — `paper-zjf`
- 自包含脚本：自动 cd 项目目录、激活 venv、运行 app.py 并透传参数。
- 装好后在任意目录输入 `paper-zjf` 即可启动，像 claude code 一样。

---

## 本轮（→ v0.7）新增：Claude Code 风格 CLI

- **`src/cli.py`**：基于 rich + prompt_toolkit 的终端界面。
  - 启动 banner、底部状态栏（当前模式 + 论文数）。
  - 斜杠命令 `/help /find /viz /matrix /papers /cache /clear /exit`，**Tab 自动补全**。
  - 带边框输入框、命令历史（↑↓）。
  - 回答用 **Markdown 渲染**，思考时显示转圈动画。
  - **流式输出**（`ask_agent_stream`，逐 token 打印）；SDK 不支持时自动回退非流式。
- **`src/commands.py`**：把 find/viz/matrix 逻辑抽成共享模块，富 CLI 与简易版共用。
- **回退策略**：`--plain` 或非交互终端 / 未装 rich 时，自动用原简易版界面。

---

## 本轮（→ v0.8）新增：多轮记忆 + /model 切换模型

- **多轮对话记忆**：`ask_agent` / `ask_agent_stream` 改为接收并返回 `history`
  （用 Agents SDK 的 `to_input_list()` 串接），追问能接上文。`/clear` 清空记忆。
  - 之前每次提问都是独立的（不记得上一轮），现在会话内保持上下文。
- **/model 切换推理模型**：`build_agent` / `build_multi_agent` 增加 `model` 参数。
  - 富 CLI：`/model` 方向键选 deepseek-chat / deepseek-reasoner / 自定义，热重建 agent，**切换不丢历史**。
  - 简易版：输入 `model` 回车后填名称。底部状态栏实时显示当前模型。
  - 默认模型可用环境变量 `DEEPSEEK_MODEL` 配置（见 `src/config.py`）。
- **实现方式**：main() 用 `agent_builder` 闭包贯通，`/model` 与 `/papers` 都通过它热重建 agent。
- **可配置论文库目录**：环境变量 `PAPERS_DIR`（见 `src/config.get_papers_dir`），设成自己的文件夹后 paper-zjf 每次自动扫描，无需把论文搬进项目；arXiv 下载也落到该目录。

---

## 下一步计划

### v0.6 — Streamlit 网页界面
- `ui/app_streamlit.py`：上传 PDF、选模板、显示带页码引用的回答。
- 侧边栏展示论文库列表与每篇论文结构（页数 / 块数）。
- 让工具从"自己用的 CLI"变成"能给别人用的产品"。

### v0.8 — 引用可点击 / 证据回溯
- 回答中的 `[p.X]` 关联到原文片段，支持展开查看检索证据。

---

## 注意事项

### 当前已知限制
1. **OCR 依赖系统 Tesseract**：未安装时扫描版 PDF 仍无法识别（会跳过并提示）。
2. **论文库索引为单机文件**：`data/index/` 不随仓库提交，换机器需重建。
3. **arXiv 下载受网络环境影响**：公司网络 / 代理下可能需要额外配置。

### DeepSeek 模型选择
- `deepseek-chat`：性价比最高，适合大多数分析任务。
- `deepseek-reasoner`：推理更强但更慢更贵；适合"审稿人挑战""研究切入点推荐"。
- 在 `src/agent.py` 的 `build_*_agent` 中修改 `model=` 参数即可切换。

### Embedding 模型选择
- 默认多语言模型，中英文论文都可用。
- 纯英文且追求速度：`export EMBEDDING_MODEL=all-MiniLM-L6-v2`。
- 切换后旧缓存自动失效（cache key 含模型名），无需手动清理。

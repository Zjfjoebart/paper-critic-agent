# ResearchOps Agent

面向科研实验流程的自动化管理助手。不是聊天 Agent，而是把做实验时最烦的重复流程标准化：

```
检查数据 → 生成配置 → 跑实验 → 监控日志 → 汇总结果 → 发现异常 → 生成下一步实验建议
```

它维护一份**实验账本**，自动检查缺失/失败实验、解析日志、汇总结果、检测异常，并生成下一批命令与阶段报告。**确定性计算（数文件、算指标、判完成）全部由 Python 完成，LLM 只做解释、判断证据、建议下一步**——避免大模型承担高风险的统计任务。

---

## 三层架构

```
第 1 层 ResearchOps Core   纯 Python，不接 LLM：扫描 / 解析 / 汇总 / 异常检测 / 报告 / 命令
第 2 层 ResearchOps Agent  接入 LLM：解释异常、判断证据、建议下一步、写报告
第 3 层 ResearchOps CLI     Claude Code 风格对话界面
```

## 快速开始

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # 填 DeepSeek API Key（仅第 2/3 层需要）
```

### 第 1 层：实验状态（不接 LLM，立即可用）

```bash
python research_ops.py status --workspace examples/vision_token_compression
```

输出到 `outputs/`：

```
experiment_status.md   阶段报告（含证据边界：已验证 / 尚未验证）
missing_runs.csv       缺失实验
failed_runs.csv        失败实验（含错误类型）
next_commands.sh       下一批命令
experiments.csv        实验账本
generated_configs/     为缺失实验生成的 config
```

### 第 2/3 层：对话式（接入 LLM）

```bash
python research_ops.py chat --workspace examples/vision_token_compression
```

交互命令：`/status`（重扫状态）、`/report`（报告路径）、`/run`（执行命令，需人工确认）、`/model`（换模型）、`/clear`、`/exit`。直接提问则由 LLM 基于工具结果解释/建议。

### 一键启动（任意目录）

```bash
chmod +x "/Users/zhangjunfeng/Desktop/项目/文献阅读器/research-ops"
echo 'alias research-ops="/Users/zhangjunfeng/Desktop/项目/文献阅读器/research-ops"' >> ~/.zshrc
source ~/.zshrc
# 之后：
research-ops status -w examples/vision_token_compression
research-ops chat   -w workspace
```

---

## 你的实验怎么接入

把你的项目按这个结构放进 `workspace/`（或任意目录，用 `-w` 指定）：

```
your_project/
├── grid.yaml        # 实验矩阵定义（各维度的取值 + 命令模板）
├── configs/         # 每个实验一个 config（yaml/json）
├── logs/            # 每个实验一个日志
└── results/         # 每个实验一个 result.json（含 metrics.accuracy 等）
```

文件命名规则：`{model}_{task}_{method}_k{keep*100:02d}_s{seed}`，
例如 `qwen2.5-vl-3b_ocr_attention_k30_s1`。`grid.yaml` 见 `examples/vision_token_compression/grid.yaml`。

---

## 安全控制（三级权限）

```
Level 0 只读        list / read configs / logs / results
Level 1 写派生文件   missing / failed / commands / report      ← 默认上限
Level 2 执行命令     训练 / 评测 / 批量任务                     ← 必须人工输入 yes 确认
```

LLM Agent 默认只能 Level 0/1，绝不删除数据、覆盖结果、自动 push 或无确认大规模启动实验。

---

## 项目结构

```
.
├── research_ops.py          # CLI 入口：status / chat
├── research-ops             # 全局启动脚本
├── agent/
│   ├── pipeline.py          # 第1层主流程（run_status）
│   ├── state.py             # 实验账本 Experiment Ledger
│   ├── safety.py            # 三级权限 + 人工确认
│   ├── prompts.py           # Agent 系统提示词
│   ├── main_agent.py        # 第2层 LLM Agent（DeepSeek）
│   ├── cli.py               # 第3层对话界面（rich + prompt_toolkit）
│   └── tools/               # 第1层确定性工具（纯 Python）
│       ├── file_tools.py    # 扫描项目
│       ├── config_tools.py  # 读配置 / 生成实验矩阵
│       ├── log_tools.py     # 日志解析（OOM / FileNotFound / NaN …）
│       ├── result_tools.py  # 汇总 / 缺失 / 异常检测
│       ├── command_tools.py # 生成 / 执行命令
│       └── report_tools.py  # 写 md / csv / sh
├── examples/vision_token_compression/   # 示例实验数据（可直接试跑）
├── workspace/               # 放你自己的实验
├── outputs/                 # 生成的派生文件
└── legacy_paper_reader/     # 归档：之前的论文阅读器（仍在 git 历史里）
```

---

## 技术选型

- Agent 框架：OpenAI Agents SDK（自带 tracing）
- 推理模型：DeepSeek（`deepseek-chat` / `deepseek-reasoner`，`/model` 可切）
- 实验追踪：先 CSV 账本，后续可接 MLflow / W&B
- 配置：YAML；日志解析：regex；命令执行：subprocess；报告：Markdown
- 界面：CLI（rich + prompt_toolkit）

## 后续方向

- [ ] 实验账本换 SQLite / 接 MLflow
- [ ] Config Planner 直接写入 workspace（带确认）
- [ ] 多 seed 的统计显著性 / 置信区间
- [ ] Streamlit 看板

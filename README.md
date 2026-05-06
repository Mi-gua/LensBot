# LensBot

> 基于大语言模型的光学镜头自动化设计智能体。LensBot 将自然语言需求、参考案例学习、可微分光学优化、Zemax 商业级性能分析和可视化界面组织成一个可迭代的本地设计工作流。

LensBot 面向光学镜头设计中的“从需求到结构再到性能验证”的闭环任务。用户可以用自然语言描述设计目标，也可以直接输入结构化参数；系统会将需求解析为焦距、视场角、F 数、后焦距、总长和面型组合等可执行设计约束，检索本地 Zemax 案例形成初始结构，然后调用 DeepLens 可微分光学引擎完成课程学习与微调优化，最后导出设计文件、分析指标、可视化图像和工程经验记忆。

## 核心特性

- 大语言模型驱动的设计智能体：使用 LLM 完成需求解析、参数提取、案例选择、初始结构建议和工程经验总结。
- ReAct 工作流：将“思考、调用工具、观察结果、继续决策”的过程显式化，形成可追踪的智能体思考轨迹。
- 案例学习与初始结构生成：基于 `cases/` 中 518 个本地 Zemax `.zmx` 案例和 `ZEMAX Index.md`，选择与目标参数相近的参考设计，并转换为 DeepLens 可用的初始结构。
- 可微分光学优化：集成 DeepLens 引擎，采用 curriculum learning 和 fine-tune 两阶段优化策略，逐步提升像质与约束满足度。
- Zemax 商业级软件性能分析：对导出的 `final.zmx` 使用 OpticStudio / ZOS-API 进行独立验证，输出 EFL、F/#、FOV、畸变、FFT MTF、MTF50、RMS / GEO spot radius、视场数、波长数、Spot Diagram 等指标与图像。
- 迭代设计闭环：需求解析、结构选择、优化、评估、验收和记忆归档构成完整循环，便于多轮实验比较。
- 可视化界面：内置本地 Web Dashboard，实时展示运行状态、时间线、结果预览、指标卡片和分析图像。
- 分层记忆系统：记录项目长期记忆、近期设计运行、可复用工程经验和当前任务上下文，让后续设计可以继承已有经验。

## 工作流

LensBot 的主流程由 `src/agent/workflow.py` 中的五个子 agent 节点组成：

1. `IntakeAgent`：读取自然语言或结构化输入，抽取镜头设计参数。
2. `SeedDesignAgent`：检索本地 Zemax 案例，学习参考结构并生成初始面型配置。
3. `OptimizationAgent`：调用 DeepLens 优化镜头，保存优化产物，并完成 DeepLens 内部指标评估。
4. `PerformanceAnalysisAgent`：对优化结果进行独立性能分析，调用 Zemax 评估商业级指标，并判断是否满足设计目标。
5. `ReportMemoryAgent`：归档结果、生成 `summary.md`、保存指标，并更新设计运行记忆与工程经验库。

整个过程会保存 `agent_trace`，用于解释每个阶段的动作与观察结果。

## 关键参数

默认参数位于 `src/agent/defaults.yaml`。主要参数包括：

| 参数 | 含义 | 默认值 |
| --- | --- | --- |
| `foclen` | 有效焦距，单位 mm | `85.0` |
| `fov` | 全视场角，单位 degree | `40.0` |
| `fnum` | F 数 | `4.0` |
| `bfl` | 后焦距，单位 mm | `18.0` |
| `thickness` | 系统总长约束，单位 mm | `120.0` |
| `surf_list` | 面型组合，包括 `Spheric`、`Aspheric`、`Aperture` 等 | 见配置文件 |

优化预算分为两阶段：

- `curriculum`：课程学习阶段，默认 `3000` 次迭代，用于从较稳定的初始条件逐步推进优化。
- `fine_tune`：微调阶段，默认 `2000` 次迭代，用于在更严格采样和损失权重下细化像质。

## 快速开始

进入项目目录：

```powershell
cd LensBot
```

安装运行所需依赖。项目当前未提供固定的 `requirements.txt`，至少需要：

```powershell
pip install openai pyyaml matplotlib pythonnet
```

DeepLens 相关依赖通常还包括 `torch`、`numpy` 等科学计算库，具体取决于本地 DeepLens 环境。若需要 Zemax 分析，还需要 Windows 环境、可用的 Ansys Zemax OpticStudio 授权，以及 ZOS-API / pythonnet 能够正常连接。

配置大语言模型接口：

```powershell
$env:LENSBOT_OPENAI_BASE_URL="https://your-api-base-url"
$env:LENSBOT_OPENAI_API_KEY="your-api-key"
$env:LENSBOT_OPENAI_MODEL="your-model-name"
```

启动本地可视化界面：

```powershell
python main.py
```

默认访问地址为：

```text
http://127.0.0.1:8000
```

如端口被占用，程序会自动尝试后续端口。也可以手动指定：

```powershell
$env:LENSBOT_PORT="8010"
python main.py
```

## 输出结果

每次设计运行会在 `results/YYYYMMDD-HHMMSS/` 下生成独立结果目录，常见文件包括：

| 文件或目录 | 说明 |
| --- | --- |
| `starting-point.json` / `starting-point.png` | 初始结构及其可视化 |
| `curriculum.json` | 课程学习阶段输出结构 |
| `curriculum/iter*.json` / `iter*.png` | 课程学习过程快照 |
| `fine-tune/iter*.json` / `iter*.png` | 微调过程快照 |
| `final.json` / `final.png` | 最终镜头结构与图像 |
| `final.zmx` | 可导入 Zemax 的最终设计文件 |
| `metrics.json` | DeepLens 与 Zemax 汇总指标 |
| `summary.md` | 自动生成的运行报告，包含输入、思考轨迹、指标和结构摘要 |
| `run.log` | 优化引擎日志 |
| `zemax-analysis/` | Zemax 报告与图像，如 `fft_mtf.png`、`spot_summary.png`、`spot_diagram.png`、`zemax_report.json` |

## 项目结构

```text
LensBot/
├── main.py                    # 本地 Web Dashboard 入口
├── cases/                     # Zemax 参考案例库与索引
├── results/                   # 自动设计运行结果
└── src/
    ├── agent/
    │   ├── workflow.py        # 多 Agent 工作流
    │   ├── loop.py            # ReAct loop 与 trace
    │   ├── prompts.py         # Agent 提示词
    │   ├── settings.py        # 参数与结果模型
    │   ├── tools.py           # 工具注册与装配
    │   ├── memory.py          # 记忆读写
    │   └── ui.py              # Dashboard 与进度流
    ├── engine/
    │   ├── deeplens/          # 可微分光学优化与评价
    │   └── zemax/             # Zemax / ZOS-API 性能分析
    ├── tools/                 # 参数解析、案例检索、优化、分析等工具适配
    └── memory/                # 项目记忆、经验库与历史运行记录
```

## 技术架构

LensBot 采用分层架构：上层是由 `workflow.py` 编排的多 Agent 工作流，负责组织需求解析、案例选择、优化、性能分析和结果归档；中间层是统一的工具注册表，将参数解析、案例检索、DeepLens 优化、Zemax 分析等能力封装为可调用工具；底层是 DeepLens 与 Zemax 两类专业引擎，分别负责可微分优化和商业级性能验证。

这种设计使 LLM 主要承担目标理解、流程调度和经验总结，数值优化与光学分析则交给确定性的工程模块执行。运行过程中，结果文件、指标、思考轨迹和工程经验会被统一归档，并通过本地 Dashboard 实时展示。

## 技术解读

LensBot 的技术路线可以概括为“语言智能体负责设计流程组织，专业光学引擎负责数值计算与性能验证”。光学镜头设计涉及连续变量优化、面型组合、材料选择、一阶参数约束和像质评价等多个层面，直接依赖大语言模型生成最终结构并不可靠。因此，项目没有把 LLM 作为光学计算器使用，而是将其放置在流程上层，用于理解设计目标、组织工具调用、迁移历史案例经验、解释中间结果，并在运行结束后总结可复用的工程知识。真正的结构优化、光线追迹、MTF 分析和 Zemax 指标验证则由确定性的专业模块完成。
             
完整数据流如下：

```text
用户输入
  -> AgentInput
  -> LensDesignParams
  -> Memory Snapshot
  -> IntakeAgent 参数确认
  -> SeedDesignAgent 案例检索与初始结构生成
  -> OptimizationAgent
  -> DeepLens curriculum 优化
  -> DeepLens fine-tune 优化
  -> final.json / final.zmx / final.png
  -> DeepLens 指标评估
  -> PerformanceAnalysisAgent
  -> Zemax / ZOS-API 商业级性能分析
  -> metrics.json / summary.md / zemax-analysis/*
  -> Design Run Memory
  -> Engineering Lessons
  -> 下一轮任务上下文
```

这一数据流体现了项目的闭环设计：前端输入首先被转化为统一任务对象，智能体再基于当前任务、项目记忆和历史经验进行阶段决策；优化结果经过 DeepLens 与 Zemax 两套评价体系验证后，被归档为结构文件、指标文件、图像文件和工程记忆，最终反向进入后续任务的上下文。

系统内部以 `LensDesignParams` 作为核心数据结构，将用户输入统一表示为焦距、视场角、F 数、后焦距、总长约束和面型组合等参数。自然语言需求会先被解析为该结构，结构化输入也会被归一化到同一数据模型中。随后，工作流根据这些参数检索本地 Zemax 案例库，选择与目标条件相近的参考设计，并从 `.zmx` 文件中提炼 DeepLens 可用的初始结构。该步骤对应传统镜头设计中的经验初始化过程，其意义在于为后续连续优化提供合理的结构起点，降低随机初始化导致的不收敛、指标漂移或结构不可用风险。

在智能体实现上，LensBot 采用节点化 ReAct 工作流，而不是单一开放式循环。`IntakeAgent`、`SeedDesignAgent`、`OptimizationAgent`、`PerformanceAnalysisAgent` 和 `ReportMemoryAgent` 分别对应需求解析、初始结构选择、优化生成、性能分析和结果归档五个阶段。每个节点只暴露当前阶段所需工具，既限制了工具调用边界，也增强了运行过程的可解释性。每轮决策中的思考、动作、输入和观察结果会被记录为 `agent_trace`，最终写入运行报告，使用户能够追踪系统如何从原始需求逐步形成可验证的镜头设计。

优化层由 `OptimizationAgent` 调度 DeepLens 可微分光学引擎完成。LensBot 将优化分为 curriculum 和 fine-tune 两个阶段：课程学习阶段侧重获得稳定可用的基本结构，微调阶段在更严格的采样与损失权重下进一步改善像质。中间迭代结果会持续保存为 JSON 和图像快照，因此用户不仅可以查看最终输出，也可以观察镜头结构和指标随迭代演化的过程。这种设计有利于分析收敛行为、定位失败原因，并支持后续实验复现。

性能验证层被独立封装为 `PerformanceAnalysisAgent`。该 Agent 在优化完成后接收 `final.zmx`、DeepLens 指标和目标参数，通过 ZOS-API 将镜头载入 Zemax / OpticStudio，进一步计算有效焦距、F 数、视场、畸变、FFT MTF、MTF50、RMS spot radius 和 GEO spot radius 等工程指标。项目会将 Zemax 指标与 DeepLens 指标合并到 `metrics.json`，并在验收逻辑中检查 EFL、FOV 和 F/# 是否偏离目标。这样可以避免仅凭局部像质改善判断设计成功，保证最终结果同时满足一阶光学参数、像质指标和工程约束。

可视化界面和记忆系统共同服务于实验可解释性。`ui.py` 通过本地 HTTP 服务和 Server-Sent Events 实时推送运行状态、时间线、结果图像和指标卡片；`memory.py` 则记录每次设计的输入、参考案例、最终结构、评估指标和经验总结。随着运行次数增加，系统能够积累关于不同焦距、视场、F 数和后焦距约束下的设计经验，使后续任务不再是孤立优化，而是建立在历史实验反馈之上的迭代式设计过程。

## 记忆机制

LensBot 的记忆分为几层：

- 项目记忆：`src/memory/project.md`，记录系统角色、工具边界和设计优先级。
- 运行记忆：`src/memory/designrun/*.json`，保存每次任务的输入、输出、指标、参考案例和最终结构摘要。
- 工程经验：`src/memory/lessons.json`，由 LLM 从成功或失败的运行中提炼可复用经验。
- 当前上下文：运行时组合最近设计、相关经验和当前目标，供各节点 Agent 决策使用。

## 适用场景

- 根据自然语言目标快速生成镜头初始结构。
- 对焦距、视场、F 数、后焦距、总长等约束进行自动化探索。
- 将本地历史 Zemax 案例转化为可学习的设计经验。
- 使用 DeepLens 进行可微分光学优化实验。
- 使用 Zemax 对最终结构进行独立的商业级指标验证。
- 记录多次迭代中的工程经验，辅助后续课程学习、微调和结构选择。

## 后续方向

- 增强参数抽取的鲁棒性，支持更多自然语言约束和制造约束。
- 扩展案例索引字段，加入焦距、FOV、镜片数、材料、像面尺寸等结构化检索信息。
- 将优化失败样本纳入经验记忆，形成更可靠的反例库。
- 增加多目标迭代策略，例如在畸变、MTF、spot size、总长和材料约束之间自动权衡。
- 完善可视化对比功能，支持多次运行之间的指标曲线和结构差异比较。
- 将 Zemax 分析结果进一步反馈到下一轮 DeepLens 优化中，形成更紧密的闭环。

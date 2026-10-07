# rerun-bench

[English](README.md) | 简体中文

[![CI](https://github.com/Abelo9996/rerun-bench/actions/workflows/ci.yml/badge.svg)](https://github.com/Abelo9996/rerun-bench/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

**同一个任务重跑几次，编程智能体每次都能通过吗？** 在 2026-10-06 的 200 次运行中（10 个任务，每个跑 10 次），Claude Code 2.1.292 搭配 claude-opus-5-5 通过了 100 次中的 100 次，Codex CLI 0.160.0 搭配 gpt-6-luna 通过了 100 次中的 96 次。Codex 的 4 次失败都一样：读取文件后没有做任何修改就正常退出，其中 3 次在最后的消息里声称已经完成了修改。两者通过率的区间仍然重叠（[96, 100] 与 [90, 98]），因此这些运行不能说明整体通过率存在差异，但它们展示了只跑一次会掩盖的东西。配置、原始运行记录和 diff 见：[docs/run-2026-10-06](docs/run-2026-10-06/README.md)。

[![2026-10-06 运行的结果卡片。Claude Code 和 Codex CLI 的 95% 区间相互重叠，因此这些运行不能说明通过率存在差异。Claude Code 搭配 claude-opus-5-5：通过率 100% [96, 100]，pass^10 100%，翻转率 0%，每次运行成本中位数 $0.0899。Codex CLI 搭配 gpt-6-luna：通过率 96% [90, 98]，pass^10 70%，翻转率 8%，成本未上报。10 个任务，每个 10 次，共 200 次运行。](https://raw.githubusercontent.com/Abelo9996/rerun-bench/main/docs/run-2026-10-06/card.png)](https://github.com/Abelo9996/rerun-bench/tree/main/docs/run-2026-10-06)

```sh
uvx rerun-bench run --agent mock --runs 5     # 免费演示：模拟智能体，无需 API key，大约 30 秒
uvx rerun-bench run --agent claude --runs 3   # 真实智能体（也可以是 codex、opencode）：先显示成本，加上 --yes 才开始
```

也可以作为 [Claude Code 插件](#作为-claude-code-插件安装)、[Codex 插件](#作为-codex-插件安装)、[GitHub Action](#在-ci-中使用)（`uses: Abelo9996/rerun-bench@v0`）使用，或通过 Homebrew 安装（`brew install abelo9996/tap/rerun-bench`）。

![rerun-bench running the free mock agent 5 times on each of 10 tasks, then printing each task's pass and fail sequence, pass rate, flip rate and cost spread](docs/demo.gif)

让每个智能体把同一个编程任务跑 N 次，看看它成功的频率有多高、在通过和失败之间来回翻转的频率有多高，以及每次运行的账单相差多少。

大多数编程智能体基准测试（SWE-bench、Terminal-Bench 及其 harbor 评测框架）报告的成功率，都来自每个任务只跑一次的结果。这个数字掩盖了你日常真正面对的情况：周一修好了某个 bug 的智能体，到了周二面对同一个任务却失败了，token 花费还翻了一倍。rerun-bench 会针对每个智能体、模型和 CLI 版本，把一套固定的、小而可验证的任务各跑若干次，然后在通过率旁边一并报告可靠性（pass^k、翻转率）和成本波动（变异系数）。

## 快速开始（免费，大约 30 秒）

`mock` 适配器会模拟一个智能体，通过概率和 token 用量都可以配置。它不花一分钱，也不需要 API key，所以在接入付费智能体之前，你可以先把整条流程完整跑一遍。

```sh
uvx rerun-bench list
uvx rerun-bench run --agent mock --tasks all --runs 5 --out results/
uvx rerun-bench report results/ --format html -o report.html
```

`run` 命令结束时会打印一段简短的汇总，以及接下来可以执行的命令；`report.html` 是一个可以直接打开或分享的独立页面。mock 的运行会标注为模拟（simulated）：其成本、token 和耗时都是虚构的。也可以用 `uv tool install rerun-bench`（或 `pipx install rerun-bench`）安装一次，之后就不用再加 `uvx` 前缀了。

Homebrew（macOS 和 Linux）：`brew install abelo9996/tap/rerun-bench`，之后直接运行 `rerun-bench list`，无需 `uvx`。

你第一次在终端里看到报告之后，rerun-bench 会打印一行字，请你在 GitHub 上点个 star。每台机器只显示一次，并在你的用户状态目录里记下已经显示过。在 CI 中、输出被管道重定向时、或使用 `--format json` 时都不会显示，也不会发送任何网络请求。设置 `RERUN_BENCH_NO_STAR_PROMPT=1` 即可关闭。

## 作为 Claude Code 插件安装

在 Claude Code 里运行：

```text
/plugin marketplace add Abelo9996/open-agent-lab
/plugin install rerun-bench@open-agent-lab
```

然后运行 `/reload-plugins` 或开一个新会话。插件会加入 rerun-bench skill 和两个命令：`/rerun-bench:run-mock [runs] [dir]` 用免费的 mock 智能体跑一遍任务集并给出汇总；`/rerun-bench:report [dir]` 汇总结果，或用 `--format html -o report.html` 写出报告。两者都通过 `uvx rerun-bench` 运行 CLI，所以只需要 [uv](https://docs.astral.sh/uv/)。这两个命令都不会启动付费的智能体运行。在终端里也可以：`claude plugin marketplace add Abelo9996/open-agent-lab`，然后 `claude plugin install rerun-bench@open-agent-lab`。

## 作为 Codex 插件安装

```sh
codex plugin marketplace add Abelo9996/open-agent-lab
codex plugin add rerun-bench@open-agent-lab
```

这会给 Codex 加入 rerun-bench skill，让它在你说“测一下这个智能体有多稳定”时运行任务集（先用 mock，只有在你确认成本之后才跑真实智能体）并解读报告。

## 运行真实的智能体

支持以下 CLI，每次都在任务工作区的一份全新临时副本中以无头（headless）模式驱动：

| 智能体 | rerun-bench 执行的命令 | CLI 是否上报成本 |
|---|---|---|
| `claude`（Claude Code） | `claude -p <prompt> --output-format json --permission-mode bypassPermissions --no-session-persistence` | 是（`total_cost_usd`） |
| `codex`（OpenAI Codex CLI） | `codex exec --json --skip-git-repo-check --ephemeral --sandbox workspace-write --cd <ws> --ignore-user-config <prompt>` | 只上报 token；通过 `--agent-opt` 传入价格即可换算成美元 |
| `opencode` | `opencode run --format json <prompt>` | 是（按步骤上报） |

```sh
rerun-bench run --agent claude --model sonnet --tasks all --runs 5 --out results/ --yes
rerun-bench run --agent codex --model <model> --runs 5 --out results/ --yes \
  --agent-opt usd_per_mtok_in=1.25 --agent-opt usd_per_mtok_out=10 --agent-opt usd_per_mtok_cached=0.125
rerun-bench report results/ --format md
```

这里的 `usd_per_mtok_*` 只是占位值；请使用你所运行模型的官方公布价格。

每次运行都会记录耗时（wall time）、退出状态、token 用量和成本（在 CLI 有上报的情况下）、CLI 版本、模型，以及最终的 diff。CLI 没有上报的值会存为 `null`，绝不会存为 0。

**成本提醒。** 真实运行会消耗你的 API 额度或订阅配额：整套任务以 `--runs 5` 运行就是 50 个智能体会话。没有 `--yes` 时，rerun-bench 会拒绝启动真实的智能体，并且会先打印运行次数，以及基于下方试点结果的大致 token 和美元估算（Claude Code 默认模型每次运行约 52,000 个 token、约 $0.09；你的模型可能更贵或更便宜）。建议从 `--tasks edit-config --runs 1` 开始。智能体会在一个临时目录中以文件编辑和 shell 权限运行；请像对待任何无人值守的智能体会话一样对待它。

默认情况下，个人配置不会影响测量结果。对于 `claude`，rerun-bench 只加载项目设置和本地设置，并忽略 `--mcp-config` 之外的 MCP 服务器，因此你自己的 hooks、插件和 MCP 服务器都不会生效。对于 `codex`，它会传入 `--ignore-user-config`，因此你 `config.toml` 里的模型、推理强度、插件和 notify hooks 都不会生效（登录认证仍然可用）。对任一智能体，都可以用 `--agent-opt isolate=0` 关闭这一行为。如果 rerun-bench 本身是在某个 Claude Code 会话里运行的，那么在启动被测的 `claude` 之前，会先移除该会话的环境变量（`CLAUDECODE`、`CLAUDE_CODE_SESSION_ID` 等）。

`codex exec --json` 不会报告它实际运行的是哪个模型，所以如果你想记录模型，请传入 `--model`；否则报告中会显示 `default`。

其他常用参数：`--jobs 4`（并行运行）、`--tasks tag:refactor` 或 `--tasks a,b`、`--keep-workspaces`（查看智能体留下了什么）、`--seed`（仅限 mock）、`--agent-opt bin=/path/to/cli`（运行某个特定构建的 CLI）、`--agent-opt effort=high`（对应 `claude --effort` 或 Codex 的 `model_reasoning_effort`）。

**配置问题会让运行停止。** 如果连续 3 次运行都以智能体错误结束（非零退出码，或 CLI 自己报告的错误，例如未登录、额度用尽或被限流），rerun-bench 会停止，打印智能体的错误信息，把这几次运行移到 `errors.jsonl`（不计分），并打印问题修复后继续运行的 `--resume` 命令。`--max-consecutive-errors 0` 可以关闭这一行为。没有导致停止的智能体错误仍然计为失败，每份报告都会写明有多少次。

耗时较长的运行可以中断后继续。按 Ctrl-C 会停止运行，保留所有已完成的运行，并打印继续运行的完整命令。用同一个 `--run-id` 加上 `--resume`，就只会运行 `runs.jsonl` 中还没有的那些（任务，运行）组合。

```sh
rerun-bench run --agent claude --tasks all --runs 3 --out results/ --run-id claude-pilot --yes
# interrupted; later:
rerun-bench run --agent claude --tasks all --runs 3 --out results/ --run-id claude-pilot --yes --resume
```

## 在 CI 中使用

这个仓库同时也是一个 GitHub Action。它会运行基准测试，把结果集和报告作为构件（artifact）上传，把文本汇总写入作业摘要（job summary），并把主要数字作为输出（outputs）提供给后续步骤。默认的智能体是 `mock`，因此无需任何配置即可运行，也不会产生任何花费。

```yaml
# .github/workflows/rerun-bench.yml
name: rerun-bench
on: [pull_request, workflow_dispatch]
permissions:
  contents: read
jobs:
  mock:
    runs-on: ubuntu-latest
    steps:
      - id: bench
        uses: Abelo9996/rerun-bench@v0
        with:
          runs: 5
      - env:
          PASS_RATE: ${{ steps.bench.outputs.pass-rate }}
          LOW: ${{ steps.bench.outputs.pass-rate-low }}
          HIGH: ${{ steps.bench.outputs.pass-rate-high }}
        run: echo "pass rate $PASS_RATE, 95% interval $LOW to $HIGH"
```

更完整的示例（包含一个只在手动触发时才运行真实智能体的作业）见 [examples/rerun-bench.yml](examples/rerun-bench.yml)。

| 输入 | 默认值 | 含义 |
|---|---|---|
| `agent` | `mock` | `mock`、`claude`、`codex` 或 `opencode`。|
| `tasks` | `all` | `all`、逗号分隔的任务 id，或 `tag:<name>`。|
| `runs` | `5` | 每个任务的运行次数。|
| `tasks-dir` | | 你仓库中的任务集目录（需要先检出代码）。留空表示使用内置任务集。|
| `version` | `0.2.0` | 通过 `uvx` 运行的 PyPI 上的 rerun-bench 版本。也可以填一个代码检出目录的路径。|
| `extra-args` | | 传给 `rerun-bench run` 的其他参数，按空白字符拆分，例如 `--model sonnet --jobs 2`。|
| `report-format` | `html` | 报告构件的格式：`html`、`md`、`json` 或 `text`。|
| `results-dir` | `rerun-bench-results` | 结果集的写入位置。|
| `artifact-name` | `rerun-bench` | 构件名为 `<name>-results` 和 `<name>-report`。如果同一次工作流运行中多次使用这个 Action（例如在 matrix 中），请设置不同的值。|

输出均为小数（0.8 表示 80%）：`pass-rate`、`pass-rate-low` 和 `pass-rate-high`（95% Wilson 区间）、`flip-rate`（每个任务只运行 1 次时为空）以及 `pass-hat-k`；另有 `k`、`runs`、`passes`、`agent-errors`、`run-dir` 和 `report-path`。后续步骤可以据此设置门槛，例如当 `pass-rate-low` 低于某个阈值时让作业失败。

**在 CI 中运行真实智能体会花钱。** 每次运行都是一个完整的智能体会话，费用计入你提供的密钥或订阅；默认设置（10 个任务、每个 5 次）就是 50 个会话，按下方试点结果中 Claude Code 默认模型计算约为 $4.40。这个 Action 会传入 `--yes`，因此不会再提示确认。请在前面的步骤中安装智能体的 CLI，并通过 Action 步骤上的 `env` 传入凭据：

| `agent` | 安装步骤 | 凭据（Action 步骤上的 `env`）|
|---|---|---|
| `mock` | 无 | 无 |
| `claude` | `npm install -g @anthropic-ai/claude-code` | `ANTHROPIC_API_KEY`（Claude Console 的密钥，按 token 计费），或通过 `claude setup-token` 生成的 `CLAUDE_CODE_OAUTH_TOKEN`（使用你的 Claude 订阅）。使用 `--agent-opt bare=1` 时只能用 `ANTHROPIC_API_KEY`。|
| `codex` | `npm install -g @openai/codex` | `CODEX_API_KEY`（OpenAI API 密钥，`codex exec` 会读取它）。|
| `opencode` | `npm install -g opencode-ai` | `--model provider/model` 中对应服务商的 API 密钥变量，例如 `ANTHROPIC_API_KEY` 或 `OPENAI_API_KEY`。|

智能体在作业中拥有 shell 权限，因此可以读取其环境中的任何变量。请使用设有消费上限的密钥，只在 Action 步骤上设置它（不要设在整个作业上），并且不要在不受信任的人可以触发的事件上运行真实智能体。从 fork 发起的工作流不会获得仓库的 secrets。

## 结果

### 2026-10-06：每个任务 10 次

全部 10 个任务，每个跑 10 次，与试点同一台 Mac：Claude Code 2.1.292 固定为 `claude-opus-5-5`，Codex CLI 0.160.0（`gpt-6-luna`），以及不指定模型的 Claude Code（在这个账号上现在上报为 `claude-opus-4-8`）。完整配置、失败分析、原始运行记录和 diff 见：[docs/run-2026-10-06](docs/run-2026-10-06/README.md)。

| 智能体 / 模型 | 通过率 [Wilson 95% CI] | pass^10 | 翻转率 | 每次运行成本中位数 | 每次运行 token 中位数 | 耗时中位数 |
|---|---|---|---|---|---|---|
| claude / claude-opus-5-5 | 100/100, 100% [96, 100] | 100% | 0% | $0.0899 | 53,368 | 12.7 s |
| codex / gpt-6-luna | 96/100, 96% [90, 98] | 70% | 8% | 未上报 | 56,552 | 16.8 s |
| claude / 默认（claude-opus-4-8） | 100/100, 100% [96, 100] | 100% | 0% | $0.1312 | 84,534 | 15.6 s |

两者通过率的区间重叠，因此这些运行不能说明整体通过率存在差异。Codex 的 4 次失败都是在 7 到 10 秒后正常退出且没有修改任何文件；其中 3 次最后的消息声称已经完成修改。

### 2026-10-03：试点

2026-10-03 针对真实 CLI 的首次运行：全部 10 个任务，每个跑 3 次，Claude Code 2.1.288（默认模型，上报为 `claude-opus-5-5`）和 Codex CLI 0.160.0（`gpt-6-luna`），运行环境为 macOS arm64。完整配置、各任务结果、原始运行记录和 diff 见：[docs/pilot-2026-10-03](docs/pilot-2026-10-03/README.md)。

| 智能体 / 模型 | 通过率 [Wilson 95% CI] | pass^3 | 翻转率 | 每次运行成本中位数 | 每次运行 token 中位数 | 耗时中位数 |
|---|---|---|---|---|---|---|
| claude / claude-opus-5-5 | 30/30, 100% [89, 100] | 100% | 0% | $0.0886 | 52,017 | 12.6 s |
| codex / gpt-6-luna | 28/30, 93% [79, 98] | 80% | 13% | 未上报 | 56,629 | 16.1 s |

每个任务 n = 3 只是一次试点，不是排行榜。两者通过率的置信区间相互重叠，因此这些运行并不能说明两个智能体之间存在差异。Claude Code 的成本是它自己按标价估算的；Codex 只上报 token。

![2026-10-03 试点的 rerun-bench 结果卡片：Claude Code 和 Codex CLI 的 95% 区间相互重叠，因此这些运行不能说明通过率存在差异。Claude Code 100% [89, 100]，pass^3 100%，翻转率 0%，每次运行成本中位数 $0.0886；Codex CLI 93% [79, 98]，pass^3 80%，翻转率 13%，成本未上报。10 个任务，每个 3 次。](docs/pilot-2026-10-03/card.svg)

## 分享卡片

`rerun-bench card` 会把一个结果目录生成为一张 1200x630 的 SVG（X、Bluesky 和链接预览使用的尺寸），就像上面这张：

```sh
uvx rerun-bench card results/                       # writes rerun-bench-card.svg
uvx rerun-bench card results/ -o my-card.svg --k 3
uvx rerun-bench card report.json                    # from a report saved with --format json
```

卡片展示每组结果的通过率，以及在同一条 0 到 100% 坐标轴上用横条加误差线画出的 95% 区间，还有 pass^k、翻转率、每次运行成本中位数、任务数和运行次数，以及日期。标题是一句关于比较结果的平实陈述，规则和报告相同：区间重叠时，它会说这些运行不能说明存在差异；区间不重叠时，它只陈述这一事实。各行按名称排序，不是排名。mock 结果会标注为 simulated（模拟）。卡片使用系统字体，并在查看器支持时跟随浅色或深色模式。

输出只有 SVG，这样 rerun-bench 依然没有任何依赖。X 和 Bluesky 需要 PNG：用 `rsvg-convert -o card.png rerun-bench-card.svg` 转换（librsvg：`brew install librsvg` 或 `apt install librsvg2-bin`），或者在浏览器里打开 SVG 截图。

## 报告示例

两个 mock 配置，10 个任务，每个跑 5 次。可以免费复现：

```sh
uvx rerun-bench run --agent mock --model mock-steady --agent-opt pass_prob=0.85 \
  --agent-opt token_cv=0.15 --runs 5 --out results/
uvx rerun-bench run --agent mock --model mock-flaky --agent-opt pass_prob=0.6 \
  --agent-opt token_cv=0.5 --runs 5 --out results/
uvx rerun-bench report results/
```

在终端中，`report` 会打印一份 80 列宽的汇总（节选）：

```
mock / mock-steady  [mock 0.2.0]
  Pass rate     80%  [67, 89]   40 of 50 runs passed
  pass^5        30%  all 5 reruns of a task pass
  pass@5       100%  at least 1 of 5 reruns passes
  Flip rate     34%  two runs of the same task disagree

mock / mock-flaky  [mock 0.2.0]
  Pass rate     60%  [46, 72]   30 of 50 runs passed
  pass^5         0%  all 5 reruns of a task pass
  pass@5       100%  at least 1 of 5 reruns passes
  Flip rate     50%  two runs of the same task disagree

Comparison
  The pass-rate 95% intervals of all rows overlap, so these runs are not enough
  to tell the rows apart. More runs per task narrow the intervals.
  ...
```

两个配置的 pass@5 都是 100%：给五次机会，每个配置都能把每个任务至少解出一次。它们的通过率区间重叠，所以仅凭通过率无法区分二者；pass^5 和翻转率反映的是它们在多次重跑之间表现得有多不一样。报告从不宣布“赢家”：区间重叠时会直接说明，不重叠时也只陈述这一事实。`--format md` 输出适合放进 README 或 PR 的 Markdown 表格，`--format json` 输出全部数值，`--format html` 输出一个内联 CSS 和 JS 的静态页面：开头是简短的“如何阅读”说明，然后是可排序的表格，以及按任务展示每次运行结果的网格。

## 指标

完整的定义、估计方法和注意事项见：[docs/METRICS.md](docs/METRICS.md)。

| 指标 | 回答的问题 |
|---|---|
| 通过率 + Wilson 95% CI | 一次运行通过隐藏验证器（verifier）的频率有多高？ |
| 任务级 bootstrap 95% CI | 同上，但把“抽到了哪些任务”这一不确定性也考虑进去（JSON 报告）。 |
| pass@k | k 次运行中至少有一次通过的概率（无偏估计）。 |
| pass^k | k 次运行全部通过的概率。如果你只跑一次就相信结果，最该关注的就是这个数字。 |
| 翻转率 | 同一任务的两次运行结果不一致的概率，即 2c(n-c)/(n(n-1))。 |
| 不稳定任务 | 既有通过又有失败的任务所占的比例。 |
| 成本 / token / 耗时 CV | 同一任务内各次运行之间的波动（标准差 / 均值），再对所有任务取平均。 |
| 每次成功的成本 | 总成本除以通过的运行次数。 |
| 解法相似度 | 通过的运行之间，改动行的两两 Jaccard 相似度的平均值。1.0 表示每次的改动都完全相同。 |
| 智能体错误、超时 | 以非零退出码、CLI 报告的错误或任务超时结束的运行。计为失败，并在每份报告中列出。 |

通过与否只由任务的验证器决定。智能体的退出码以及它自称成功的说法会被记录下来，但不计入评分。一份报告包含多个结果集时，pass@k 和 pass^k 对每一行使用相同的 k：取各结果集中每任务运行次数的最小值（可用 `--k` 调低）。

## 任务集

`rerun-bench list` 会列出内置的任务：

| 任务 | 考察内容 |
|---|---|
| `fix-failing-test` | 在不修改测试的前提下，修复导致单元测试失败的 bug |
| `implement-slugify` | 严格按照 docstring 规范实现一个函数 |
| `implement-lru-cache` | 按规范实现一个小型数据结构 |
| `refactor-extract-helper` | 提取重复逻辑；在一组输入上检查行为是否一致 |
| `follow-agents-md` | 添加一个函数；prompt 中不会提到仓库里 AGENTS.md 的规则，但验证器会检查这些规则 |
| `edit-config` | 对 TOML 做三处精确修改；旁边的生产环境配置必须保持原样 |
| `multi-file-rename` | 在整个包中重命名一个函数，不能留下任何别名 |
| `minimal-fix` | 在一段刻意写得很老旧的代码里修一个单行 bug；对该函数之外做任何清理都算失败 |
| `add-cli-flag` | 添加一个参数，且不改变默认输出 |
| `write-tests` | 编写在真实代码上能通过、并且能抓出五个注入 bug 的测试（变异测试） |

每个任务都离线运行、结果确定，并且只使用 Python 标准库，所以在 Linux、macOS 和 Windows 上的表现完全一致。

## 添加任务

```
tasks/<id>/
  task.toml      id, title, prompt, timeout (seconds), tags
  workspace/     the files the agent starts with
  verify.py      exit 0 = pass; runs with cwd = the agent's workspace; never shown to the agent
  solution/      reference solution, copied over workspace/ by the test suite
```

```toml
id = "my-task"
title = "One line describing the task"
prompt = """
What you would type to the agent.
"""
timeout = 600
tags = ["bugfix", "python"]
```

然后在仓库根目录下检查：`uv run rerun-bench --tasks-dir tasks verify-tasks --tasks my-task -v` 必须输出 `ok`（未经修改的工作区不通过，参考答案通过），并且 `uv run pytest` 会自动把新任务纳入测试。如果要在仓库之外运行你自己的任务集，把 `--tasks-dir <路径>` 放在子命令之前：`uvx rerun-bench --tasks-dir my-tasks run --agent mock --runs 3`。验证器的编写规则见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 添加适配器

在 `src/rerun_bench/adapters/` 中继承 `Adapter`，实现两个纯方法，然后在 `src/rerun_bench/adapters/__init__.py` 的 `ADAPTERS` 中注册：

```python
# src/rerun_bench/adapters/myagent.py
import json
from pathlib import Path

from .base import Adapter, Usage


class MyAgentAdapter(Adapter):
    name = "myagent"
    binary = "myagent"

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        return [self.binary, "run", "--json", prompt]

    def parse_output(self, stdout: str, stderr: str) -> Usage:
        # Fill tokens, cost and model; leave a field None when the CLI does not report it.
        data = json.loads(stdout)
        return Usage(output_tokens=data.get("output_tokens"), cost_usd=data.get("cost"))
```

子进程、超时、耗时统计、`--version`，以及把非零退出码记录为智能体错误，都由基类处理。除 `mock` 之外的每个适配器都被视为付费智能体，所以 `run` 在启动前会要求 `--yes`。请用一份采集到的 CLI 输出样本来测试这两个方法（参见 `tests/test_adapters.py`）；测试套件从不调用真实的智能体。

## Agent Skill

`skills/rerun-bench/SKILL.md` 会教编程智能体如何运行这套基准测试以及如何添加任务：

```sh
npx skills add Abelo9996/rerun-bench
```

## 路线图

- 公开排行榜，在新模型发布当天更新，基于 HTML 报告生成。
- 跨版本追踪：同一个模型在连续多个 CLI 版本下的表现，并对每个任务做显著性检验。
- 两组结果之间的配对比较（每个任务用 Fisher 精确检验，整套任务用任务级 bootstrap）。
- 增加更多其他语言的任务，同样保持小巧、离线、结果确定。

## 相关项目

- [nerf-watch](https://github.com/Abelo9996/nerf-watch)：从本地的智能体日志中，检测悄无声息的模型变化和成本变化。
- [snap-back](https://github.com/Abelo9996/snap-back)：适用于任何编程智能体的撤销功能。

## 开发

```sh
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run rerun-bench verify-tasks
```

采用 MIT 许可证。参见 [LICENSE](LICENSE)。

如本文与英文版 [README](README.md) 有出入，以英文版为准。

# rerun-bench

[English](README.md) | 简体中文

[![CI](https://github.com/Abelo9996/rerun-bench/actions/workflows/ci.yml/badge.svg)](https://github.com/Abelo9996/rerun-bench/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

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

也可以用 `uv tool install git+https://github.com/Abelo9996/rerun-bench` 安装一次，之后就不用再加 `uvx --from ...` 前缀了。

## 运行真实的智能体

支持以下 CLI，每次都在任务工作区的一份全新临时副本中以无头（headless）模式驱动：

| 智能体 | rerun-bench 执行的命令 | CLI 是否上报成本 |
|---|---|---|
| `claude`（Claude Code） | `claude -p <prompt> --output-format json --permission-mode bypassPermissions` | 是（`total_cost_usd`） |
| `codex`（OpenAI Codex CLI） | `codex exec --json --ephemeral --ignore-user-config --sandbox workspace-write --cd <ws> <prompt>` | 只上报 token；通过 `--agent-opt` 传入价格即可换算成美元 |
| `opencode` | `opencode run --format json <prompt>` | 是（按步骤上报） |

```sh
rerun-bench run --agent claude --model sonnet --tasks all --runs 5 --out results/ --yes
rerun-bench run --agent codex --model <model> --runs 5 --out results/ --yes \
  --agent-opt usd_per_mtok_in=1.25 --agent-opt usd_per_mtok_out=10 --agent-opt usd_per_mtok_cached=0.125
rerun-bench report results/ --format md
```

这里的 `usd_per_mtok_*` 只是占位值；请使用你所运行模型的官方公布价格。

每次运行都会记录耗时（wall time）、退出状态、token 用量和成本（在 CLI 有上报的情况下）、CLI 版本、模型，以及最终的 diff。CLI 没有上报的值会存为 `null`，绝不会存为 0。

**成本提醒。** 真实运行会消耗你的 API 额度或订阅配额：整套任务以 `--runs 5` 运行就是 50 个智能体会话。没有 `--yes` 时，rerun-bench 会拒绝启动真实的智能体，并且会先打印运行次数。建议从 `--tasks edit-config --runs 2` 开始。智能体会在一个临时目录中以文件编辑和 shell 权限运行；请像对待任何无人值守的智能体会话一样对待它。

默认情况下，个人配置不会影响测量结果。对于 `claude`，rerun-bench 只加载项目设置和本地设置，并忽略 `--mcp-config` 之外的 MCP 服务器，因此你自己的 hooks、插件和 MCP 服务器都不会生效。对于 `codex`，它会传入 `--ignore-user-config`，因此你 `config.toml` 里的模型、推理强度、插件和 notify hooks 都不会生效（登录认证仍然可用）。对任一智能体，都可以用 `--agent-opt isolate=0` 关闭这一行为。如果 rerun-bench 本身是在某个 Claude Code 会话里运行的，那么在启动被测的 `claude` 之前，会先移除该会话的环境变量（`CLAUDECODE`、`CLAUDE_CODE_SESSION_ID` 等）。

`codex exec --json` 不会报告它实际运行的是哪个模型，所以如果你想记录模型，请传入 `--model`；否则报告中会显示 `default`。

其他常用参数：`--jobs 4`（并行运行）、`--tasks tag:refactor` 或 `--tasks a,b`、`--keep-workspaces`（查看智能体留下了什么）、`--seed`（仅限 mock）、`--agent-opt bin=/path/to/cli`（运行某个特定构建的 CLI）、`--agent-opt effort=high`（对应 `claude --effort` 或 Codex 的 `model_reasoning_effort`）。

耗时较长的运行可以中断后继续：用 `--run-id` 给这次运行命名，再加上 `--resume`，就只会运行 `runs.jsonl` 中还没有的那些（任务，运行）组合。

```sh
rerun-bench run --agent claude --tasks all --runs 3 --out results/ --run-id claude-pilot --yes
# interrupted; later:
rerun-bench run --agent claude --tasks all --runs 3 --out results/ --run-id claude-pilot --yes --resume
```

## 试点结果

2026-10-03 针对真实 CLI 的首次运行：全部 10 个任务，每个跑 3 次，Claude Code 2.1.288（默认模型，上报为 `claude-opus-5-5`）和 Codex CLI 0.160.0（`gpt-6-luna`），运行环境为 macOS arm64。完整配置、各任务结果、原始运行记录和 diff 见：[docs/pilot-2026-10-03](docs/pilot-2026-10-03/README.md)。

| 智能体 / 模型 | 通过率 [Wilson 95% CI] | pass^3 | 翻转率 | 每次运行成本中位数 | 每次运行 token 中位数 | 耗时中位数 |
|---|---|---|---|---|---|---|
| claude / claude-opus-5-5 | 30/30, 100% [89, 100] | 100% | 0% | $0.0886 | 52,017 | 12.6 s |
| codex / gpt-6-luna | 28/30, 93% [79, 98] | 80% | 13% | 未上报 | 56,629 | 16.1 s |

每个任务 n = 3 只是一次试点，不是排行榜。两者通过率的置信区间相互重叠，因此这些运行并不能说明两个智能体之间存在差异。Claude Code 的成本是它自己按标价估算的；Codex 只上报 token。

## 报告示例

两个 mock 配置，10 个任务，每个跑 5 次（`rerun-bench report results/`）：

| 智能体 / 模型 | 每任务运行次数 | 通过率 [95% CI] | pass@k | pass^k | 翻转率 | 不稳定任务 | 每次运行成本 | 成本 CV |
|---|---|---|---|---|---|---|---|---|
| mock / mock-steady | 5 | 86% [74, 93] | 100% | 40% | 26% | 60% | $0.0601 | 0.19 |
| mock / mock-flaky | 5 | 60% [46, 72] | 100% | 0% | 50% | 100% | $0.0906 | 0.46 |

| 任务 | mock / mock-steady | mock / mock-flaky |
|---|---|---|
| fix-failing-test | `PPPPP` 100%, flip 0%, cost CV 0.13 | `FFFPF` 20%, flip 40%, cost CV 0.49 |
| minimal-fix | `PPPPF` 80%, flip 40%, cost CV 0.16 | `PPFPF` 60%, flip 60%, cost CV 0.46 |

两个配置的 pass@5 都是 100%：给五次机会，每个配置都能把每个任务至少解出一次。真正能把它们区分开的，只有 pass^5 和翻转率。HTML 报告（`--format html`）是一个单独的静态文件，内联了 CSS 和 JS，包含一个可排序的排行榜，以及按任务展示每次运行结果的网格。

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

通过与否只由任务的验证器决定。智能体的退出码以及它自称成功的说法会被记录下来，但不计入评分。

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

然后检查一下：`rerun-bench --tasks-dir tasks verify-tasks --tasks my-task -v` 必须输出 `ok`（未经修改的工作区不通过，参考答案通过），并且 `uv run pytest` 会自动把新任务纳入测试。验证器的编写规则见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 添加适配器

在 `src/rerun_bench/adapters/` 中继承 `Adapter`，实现两个纯方法，然后在 `src/rerun_bench/adapters/__init__.py` 的 `ADAPTERS` 中注册：

```python
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

子进程、超时、耗时统计和 `--version` 都由基类处理。请用一份采集到的 CLI 输出样本来测试这两个方法（参见 `tests/test_adapters.py`）；测试套件从不调用真实的智能体。

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

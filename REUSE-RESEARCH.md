# StyleForge：上游源码复用调研

调研日期：2026-11-19
调研范围：五个指定 GitHub 仓库的浅克隆源码、Skill 入口、实际实现、测试与许可证；并与本地 `D:\AI\codex\styleforge` 当前实现逐项对照。

## 结论摘要

没有一个上游仓库同时提供“作者风格学习 + CTF 求解过程记账 + 有证据来源的带图 WriteUp”。目前最完整的底座仍是 StyleForge 自己：它已把 `Learn/Write` 与 `Solve/Replay` 分开，保存个人作者档案、过程事件、原始命令输出、截图证据及候选/已批准文章。

最值得吸收的是**实现模式**，而非整包搬入：

1. 用 `agent-skills` 的“声音、节奏、结构、标志性写法、反模式、代表文章”维度检查 StyleForge 的风格学习覆盖度；其内容是手工编写的单作者样例，不是多文档分析程序，而且仓库没有许可证。
2. 用 `record-and-replay-skill` 的 selector 候选、事件时间线、Trace 分块及显式暂停设计改善可选的浏览器过程记录；不要把其全局桌面键盘监听直接并入常态流程。
3. `ctf-skills` 的“从原始题目输入到最终 Flag 的单一完整脚本 + 实际输出”适合作为 Write Mode 的可复现性检查项，不要把其统一短模板强加给所有 Style Profile。
4. `playwright-skill` 的工具启动器和可配置截图 helper 是 MIT 许可下可复用的浏览器工程参考；当前 StyleForge 已有 Python Playwright 截图路径，直接增加 Node 工具链的收益有限。
5. `auto-ctf-solver` 确实有 Markdown / DOCX 生成源码，但图片只按会话目录收集并集中放在文章末尾，缺少步骤、证据项和命令的关联。仓库缺少 LICENSE 文件；虽 `pyproject.toml` 标注 MIT，直接复制源码前仍应确认授权。

本次只做源码调查和报告，没有复制、覆盖或修改 StyleForge 代码，也没有运行上游仓库脚本。上游快照保存在当前工作目录的 `work/reuse-research-20261119/repos/`，以下 GitHub 链接固定到本次读取的 commit。

## 能力对照

标记含义：**代码实现** = 仓库中有相应运行代码；**Skill/文档** = 主要是给 Agent 的操作说明；**未实现** = 本次检查范围未发现功能代码。

| 仓库 | 风格画像 | CTF WP | 截图与过程记录 | 可复用判断 |
|---|---|---|---|---|
| [ctf-skills](https://github.com/not-narleeek/ctf-skills/tree/08f44e839cb3826e7f4f5376f42591234d430a17) | 无个人 Profile；写作 Skill 文本 | Skill 提供步骤、脚本和真实性清单；没有 WP 渲染器 | 只把截图/输出当输入材料，无事件捕获器 | MIT；借鉴可复现性规则，适配后采用 |
| [auto-ctf-solver](https://github.com/Jiaerhan/auto-ctf-solver/tree/a09da7dc2526ed4c38adaefb8c37b464105536fc) | 无 | 有 Python Markdown 与 DOCX writer | 有 Docker 中截图调用；无步骤级证据 manifest | 可借鉴输出能力；许可证需先澄清，不直接复制 |
| [record-and-replay-skill](https://github.com/ugarchance/record-and-replay-skill/tree/5e6b52ecb097df67eb1c94e83abfd5f39c663ef5) | 从演示归纳工作流 Skill，不是文章风格 Profile | 将已录制事件交 Agent 整理；不是 CTF 求解日志格式 | Browser Playwright 事件/Trace、desktop 全局输入及点击截图有代码 | MIT；浏览器模式借鉴，桌面录制只做显式 opt-in |
| [agent-skills](https://github.com/kriss-045/agent-skills/tree/b74b9d7b9dc9534607fe64e7a78fe053a1c0f8a1) | 单作者的手写风格参考文档 | 单作者文章生成 Skill | 未实现截图采集 | 无 LICENSE；只借鉴分类维度，不复制档案文本 |
| [playwright-skill](https://github.com/lackeyjb/playwright-skill/tree/dd47a6a023e249eb1b36e9e943eab89d0900865d) | 无 | 无 | Playwright 截图 helper 和 runner 有代码；不记录用户操作流 | MIT；按需复用 helper 模式，StyleForge 已有实现可优先沿用 |

## 逐仓库源码发现

### 1. ctf-skills：短而完整的可复现写作规则

**实际实现。** 仓库主要是 `skills/<category>/SKILL.md` 和少量验证脚本。`ctf-writeup/SKILL.md` 要求先收集 challenge 元数据、EXP、Payload、截图、输出和关键时间线；之后选择一条完整路径，优先让脚本从附件直接到 Flag，并展示真实输出。它还明确反对多个半成品代码片段、裸贴终端 dump 和无关背景。详见 [ctf-writeup/SKILL.md](https://github.com/not-narleeek/ctf-skills/blob/08f44e839cb3826e7f4f5376f42591234d430a17/skills/ctf-writeup/SKILL.md#L23-L42)、[模板和完整脚本要求](https://github.com/not-narleeek/ctf-skills/blob/08f44e839cb3826e7f4f5376f42591234d430a17/skills/ctf-writeup/SKILL.md#L46-L102)、[质量清单](https://github.com/not-narleeek/ctf-skills/blob/08f44e839cb3826e7f4f5376f42591234d430a17/skills/ctf-writeup/SKILL.md#L106-L135)。`solve-challenge/SKILL.md` 负责分类、调用专题 Skill，解题后再调用 writeup Skill，而不是在一个大提示里装入全部知识：[分类和写作交接](https://github.com/not-narleeek/ctf-skills/blob/08f44e839cb3826e7f4f5376f42591234d430a17/skills/solve-challenge/SKILL.md#L115-L185)。

**不是实现的部分。** 这套 WP 是提示词和 Markdown 模板，不会读取运行时事件、绑定 Flag 来源、生成文档或截屏。`scripts/validate-skills.py` 验证的是 frontmatter 字段、名称和描述长度，不是写作质量或脚本可运行性：[validator](https://github.com/not-narleeek/ctf-skills/blob/08f44e839cb3826e7f4f5376f42591234d430a17/scripts/validate-skills.py#L1-L15)。

**借鉴方式。** MIT，仓库包含标准 [LICENSE](https://github.com/not-narleeek/ctf-skills/blob/08f44e839cb3826e7f4f5376f42591234d430a17/LICENSE)。从中吸收“完整 EXP + 实际输出 + 关键依赖前置”作为轻量 QA 项；保留 StyleForge 的按题目复杂度规划结构，不照搬固定的 1–3 步、短篇提交模板。

### 2. auto-ctf-solver：能生成文件，但图片与过程脱节

**实际实现。** `WriteupGenerator.generate()` 读取结构化 solve result、汇总 screenshot manager 当前列出的 PNG，再选择 `MdWriter` 或 `DocxWriter` 输出：[generator.py](https://github.com/Jiaerhan/auto-ctf-solver/blob/a09da7dc2526ed4c38adaefb8c37b464105536fc/src/auto_ctf/writeup/generator.py#L16-L94)。Markdown writer 生成 Summary/Approach/Steps/Flag 一类固定章节；DOCX writer 通过 `python-docx` 写标题、段落及嵌图：[md_writer.py](https://github.com/Jiaerhan/auto-ctf-solver/blob/a09da7dc2526ed4c38adaefb8c37b464105536fc/src/auto_ctf/writeup/md_writer.py#L8-L75)、[docx_writer.py](https://github.com/Jiaerhan/auto-ctf-solver/blob/a09da7dc2526ed4c38adaefb8c37b464105536fc/src/auto_ctf/writeup/docx_writer.py#L12-L77)。截图路径调用 Docker 内 `scrot`、ImageMagick `import` 和 CutyCapt：[screenshot.py](https://github.com/Jiaerhan/auto-ctf-solver/blob/a09da7dc2526ed4c38adaefb8c37b464105536fc/src/auto_ctf/tools/screenshot.py#L13-L80)。watcher 在检测到文件后可自动 solve 并生成 WP：[watcher.py](https://github.com/Jiaerhan/auto-ctf-solver/blob/a09da7dc2526ed4c38adaefb8c37b464105536fc/src/auto_ctf/watcher.py#L18-L101)。

**实现边界。** 截图 manager 的 `list_screenshots()` 收集整个 screenshot 目录的所有 PNG，生成器再整体附加；Markdown 和 DOCX writer 都把图片集中放在文末，没有证据 ID、case step、命令、截图源和文章段落间的绑定。Markdown 每 step 截到 3000 字符，DOCX 每 step 截到 2000 字符，这会静默截断长 EXP/推导。writer 忽略的字段和实际采用的章节以源码为准，不应仅凭 `docs/EVIDENCE.md` 的产品描述推断生成质量。测试目录只有知识库/Agent/prompt coverage 为主的测试，没有发现这些 writer 与真实截图关联的专门测试：[测试文件](https://github.com/Jiaerhan/auto-ctf-solver/blob/a09da7dc2526ed4c38adaefb8c37b464105536fc/tests/test_patterns_coverage.py#L31-L90)。

**依赖与许可证。** `pyproject.toml` 包含 Anthropic SDK、python-docx、Pillow、watchdog、rich、Docker SDK、httpx、Markdown 和 BeautifulSoup：[依赖声明](https://github.com/Jiaerhan/auto-ctf-solver/blob/a09da7dc2526ed4c38adaefb8c37b464105536fc/pyproject.toml#L1-L43)。GitHub API 未识别 license，检出的仓库根目录也没有 `LICENSE` 文件；`pyproject.toml` 与 README 声明 MIT。这是元数据/仓库文本有声明但缺少授权文本文件的状态，不把它当成已核实的可直接复制许可。适合参考 writer 分层，不建议 StyleForge 引入其整套求解应用或直接复制代码。

### 3. record-and-replay-skill：丰富的真实事件记录，捕获范围也更大

**浏览器实现。** `scripts/recorder.mjs` 用 Playwright 启动 headed Chrome，记录带序号和相对时间的 `events.jsonl`、session 元数据及分块 `trace-NNN.zip`；可以选择 `light/full/off` Trace 模式。元素事件会记录多种 selector 候选（test id、id、role/name、文本、CSS），留给后续选最稳定位器：[selector 生成](https://github.com/ugarchance/record-and-replay-skill/blob/5e6b52ecb097df67eb1c94e83abfd5f39c663ef5/scripts/recorder.mjs#L278-L312)。暂停时事件流与 Trace 一起停止，resume/stop 记录 session markers，最终分块 Trace 可供检查：[暂停和 Trace 生命周期](https://github.com/ugarchance/record-and-replay-skill/blob/5e6b52ecb097df67eb1c94e83abfd5f39c663ef5/scripts/recorder.mjs#L586-L705)。`summarize.mjs` 把事件变成时间顺序摘要，但原始 JSONL 仍是主证据：[summarizer](https://github.com/ugarchance/record-and-replay-skill/blob/5e6b52ecb097df67eb1c94e83abfd5f39c663ef5/scripts/summarize.mjs#L42-L160)。`replay-template.mjs` 是可编辑的重放脚手架，依赖 Agent 将观察到的动作整理成脚本，不是自动把原始事件无损回放的通用引擎：[replay template](https://github.com/ugarchance/record-and-replay-skill/blob/5e6b52ecb097df67eb1c94e83abfd5f39c663ef5/scripts/replay-template.mjs#L1-L41)。

**桌面实现和 Windows。** Node 驱动辨认 `win32` 并选取 venv 的 `Scripts/python.exe`；桌面引擎用 `pynput` 监听输入、`mss`/Pillow 在 click moment 保存半尺寸 JPEG，并将重活放在 worker thread。源码按 macOS、Windows、Linux 分支处理 active window；Linux 限于 X11：[driver](https://github.com/ugarchance/record-and-replay-skill/blob/5e6b52ecb097df67eb1c94e83abfd5f39c663ef5/scripts/desktop-record.mjs#L32-L55)、[桌面事件与截图](https://github.com/ugarchance/record-and-replay-skill/blob/5e6b52ecb097df67eb1c94e83abfd5f39c663ef5/scripts/desktop-lite-recorder.py#L171-L253)、[窗口和输入事件](https://github.com/ugarchance/record-and-replay-skill/blob/5e6b52ecb097df67eb1c94e83abfd5f39c663ef5/scripts/desktop-lite-recorder.py#L256-L364)。setup 用 Node/npm/Playwright，并可用 `uv` 建 Python 3.12 桌面 venv：[setup](https://github.com/ugarchance/record-and-replay-skill/blob/5e6b52ecb097df67eb1c94e83abfd5f39c663ef5/setup.mjs#L1-L97)。仓库附浏览器和桌面 self-test；本次未运行它们。

**借鉴与限制。** MIT，根目录有 [LICENSE](https://github.com/ugarchance/record-and-replay-skill/blob/5e6b52ecb097df67eb1c94e83abfd5f39c663ef5/LICENSE)。可按需吸收时间戳事件序列、selector 候选、暂停标记、分块及人工复核的做法，不复用整套“录屏/监听”代替 StyleForge 的 `casebook`。浏览器密码遮罩是启发式，Trace 不保证遮罩；desktop 模式不遮罩任何键盘输入或截图。其全局输入覆盖面远大于 WP 需要的关键步骤采证，不应无提示自动开启。StyleForge 现有 `evidence_capture` 按指定 step 做单次真实截图并写 evidence manifest，更贴合“少而关键、可追溯”的要求。

### 4. agent-skills：细粒度风格维度范例，不是风格提取器

仓库中的 `skills/kriss-writing-style/SKILL.md` 与 `references/` 将一位作者的 voice、tone/rhythm、结构套路、signature moves、代表文章和 anti-pattern 拆成多个按需加载的文档；`kriss-article-writer/SKILL.md` 再按 outline、用户确认、draft、QA 和润色顺序使用这些参考：[style skill](https://github.com/kriss-045/agent-skills/blob/b74b9d7b9dc9534607fe64e7a78fe053a1c0f8a1/skills/kriss-writing-style/SKILL.md#L1-L65)、[voice/rhythm](https://github.com/kriss-045/agent-skills/blob/b74b9d7b9dc9534607fe64e7a78fe053a1c0f8a1/skills/kriss-writing-style/references/voice-tone-and-rhythm.md#L1-L96)、[signature moves](https://github.com/kriss-045/agent-skills/blob/b74b9d7b9dc9534607fe64e7a78fe053a1c0f8a1/skills/kriss-writing-style/references/signature-moves.md#L1-L120)、[文章流程](https://github.com/kriss-045/agent-skills/blob/b74b9d7b9dc9534607fe64e7a78fe053a1c0f8a1/skills/kriss-article-writer/SKILL.md#L1-L90)。

这些是**为特定作者手工维护的规则和范文**：没有历史文章 ingest/parser、自动量化、Profile CRUD、多作者隔离或检索服务。风格规律由作者顾问/Agent 提炼并写成 Markdown，并非代码自动从 N 篇文章学习。GitHub API 无 license 元数据；浅克隆根目录也没有 LICENSE/COPYING。可以参考“风格维度”和“人工 outline/二次编辑”这种流程设计，不能复制其作者的独特措辞或个人档案文本。更合适的 StyleForge 产物是引用 sample ID 的多维 Profile，并明确哪些是计算统计、哪些是 Agent 定性判断、哪些是用户偏好。

### 5. playwright-skill：浏览器脚本执行与截图 helper

这是实际可加载的 Skill，也有 `run.js` 和 `lib/helpers.js`。`run.js` 将用户脚本以 Node 子进程启动、保留调用者 CWD、透传 stdout/stderr/退出码，并可把脚本副本保存到 `PW_SCRIPT_DIR`：[runner](https://github.com/lackeyjb/playwright-skill/blob/dd47a6a023e249eb1b36e9e943eab89d0900865d/skills/playwright-skill/run.js#L10-L96)。`takeScreenshot()` 用 Playwright 对当前实际 browser page 调 `page.screenshot()`，以 ISO 时间命名并返回真实文件路径：[helper](https://github.com/lackeyjb/playwright-skill/blob/dd47a6a023e249eb1b36e9e943eab89d0900865d/skills/playwright-skill/lib/helpers.js#L54-L65)。Skill 文档描述使用可见 Chromium、页面动作及截图：[skill workflow/example](https://github.com/lackeyjb/playwright-skill/blob/dd47a6a023e249eb1b36e9e943eab89d0900865d/skills/playwright-skill/SKILL.md#L37-L102)。

**边界与测试。** 它不记录用户先前的操作事件，不做 CTF 推理、证据 manifest 或作者风格。依赖 Node >=20 和 Playwright，首次 setup 下载浏览器：[package.json](https://github.com/lackeyjb/playwright-skill/blob/dd47a6a023e249eb1b36e9e943eab89d0900865d/skills/playwright-skill/package.json#L1-L28)。MIT 且带根 LICENSE。测试覆盖 runner 退出码、CWD、脚本副本与 helper 环境；截图测试 mock page 并写一个文本文件作为输出，不是浏览器真实截图验证；smoke test 则对本地 fixture 做真实浏览器交互：[tests](https://github.com/lackeyjb/playwright-skill/blob/dd47a6a023e249eb1b36e9e943eab89d0900865d/tests/executor.test.js#L10-L104)、[helper tests](https://github.com/lackeyjb/playwright-skill/blob/dd47a6a023e249eb1b36e9e943eab89d0900865d/tests/helpers.test.js#L10-L81)、[smoke test](https://github.com/lackeyjb/playwright-skill/blob/dd47a6a023e249eb1b36e9e943eab89d0900865d/tests/smoke.js#L1-L32)。

可以在 StyleForge 的 Playwright 后端抽象里参考“按需启动浏览器 / 复用调用者 CWD / 统一产物目录 / 截图路径返回值”；现有 [evidence_capture.py](scripts/evidence_capture.py#L94) 已使用 Python Playwright，额外引入 Node runtime 不是优先项。

## 与现有 StyleForge 的对应关系

本地当前版本已具备以下基础能力，先扩展既有边界，不另造一套仓储：

- `style_profiles.py` 解析 Markdown/TXT/HTML/DOCX/PDF、保存原样样本与附件、按作者 ID 校验，并为句长/段落、章节、代码、词汇计数和图片位置/宽度/注释/终端/源码习惯建立指标；见 [解析及图片/文本度量](scripts/style_profiles.py#L51)、[Profile 学习与样本归档](scripts/style_profiles.py#L188)、[Profile 编辑/导出/反馈](scripts/style_profiles.py#L267)。PDF/DOCX 的图片语义和布局仍要求 Agent 检查；自动量化不等于语义风格学习。
- `publishing.prepare()` 当前按导入顺序取前 N 篇样本片段，不是按主题/题型检索的代表性表达；写作包明确把定性风格判断交 Agent 做。见 [prepare 与 sample excerpt](scripts/publishing.py#L23-L51)、[style diagnostics](scripts/publishing.py#L54-L68)。这是对 StyleForge 最具体的可改进点：按作者 Profile 内样本指标和题目类型挑代表材料，输出带 sample ID、来源、哈希及摘录位置的引用包；不可跨 profile 检索。
- `casebook.py` 将 `style_mode` 与 `record_mode` 分字段保存、允许独立切换；历史 Replay 与首次 Solve 使用不同来源说明：[case init/switch](scripts/casebook.py#L123-L183)。
- `sf_core.py` 的 append-only `events.jsonl` 含 sequence、timestamp、owner、mode、previous/event SHA-256 链：[event hash chain](scripts/sf_core.py#L147-L194)。命令运行保存原始 stdout/stderr bytes、退出状态、timeout 和脚本身份检查：[run / EXP check](scripts/casebook.py#L201-L370)。
- `evidence_capture.py` 会先探测当前 screenshot 后端；Playwright 浏览器页与 Windows native visible window/console 是不同 capture route，失败转 unavailable/manual import，而非生成假图：[capability probe](scripts/evidence_capture.py#L18-L56)、[browser/desktop capture](scripts/evidence_capture.py#L94-L162)、[real Windows console](scripts/evidence_capture.py#L164-L224)。
- `publishing.py` 将 `<!-- evidence:ID -->` 绑定到指定 case event、原始图像 hash、文章引用和归档 bundle；候选文章与实际用户批准分离：[evidence validation](scripts/publishing.py#L227-L300)、[candidate publish](scripts/publishing.py#L306-L401)、[approval and offline verification](scripts/publishing.py#L430-L535)。主发布格式为 Markdown；本地 `python-docx` 当前供 DOCX 样本导入，不是 writer。

当前源代码入口为 [SKILL.md](SKILL.md)，不是独立 Web/桌面产品。StyleForge 仓库中的隔离 fixture 回归本轮执行 `python -m pytest -q`，结果为 43 passed；本次 GitHub 调研未执行上游脚本。

## 推荐集成优先级

| 优先级 | 建议 | 做法与验收依据 |
|---|---|---|
| P0 | 保持 StyleForge 作为唯一写作/证据仓 | 不复制 auto solver 的 global screenshot collection、统一固定章节或另外建第二份 event store。继续复用现有 profile/case/evidence 数据模型与单次 capability probe。 |
| P0 | 把“完整脚本 + 实际输出 + 可重跑”作为 Word 文本 QA | 采纳 ctf-skills 的一条完整 solution path 和真实 stdout 要求；由现有 run/EXP source 绑定支持，不能因为模板里出现 Flag 就判定 solve 成功。 |
| P1 | 增强 Profile 内代表样本检索 | 现在 `prepare` 取导入序前几篇。增加按题型/文章结构/语言、图片模式和代表性指标的可解释排序；返回 sample ID、摘录和哈希，允许用户查看选择依据。短语检索可先本地轻量实现，embedding 作为可选且可禁用后端。 |
| P1 | 把文字风格画像与写作意图分开保存 | 画像按样本 ID 记录 tone、句节奏、段落、结构、推理叙述、代码展示、Markdown、图片及反模式；用户 preferences 单独存储。词频和平均长度只作诊断信号，Agent 定性结论必须指向具体样本。 |
| P1 | 保留 evidence manifest 为图片与正文之间的权威关联 | 对每张真实图记录 step ID、来源/后端、命令或操作、时间、hash、截图说明、用户确认状态；文章将图片嵌在相关判断旁，发布检查验证相对路径与原图一致。现有实现已如此设计，上游无需搬进。 |
| P2 | 有真实需求时增加浏览器操作事件源 | 仅在用户显式开启 Solve&Write 记录时，将 Playwright 事件/Trace 导入 StyleForge case step；先支持 pause 和结束/丢弃，再摘要并人工选择关键节点。原始 Trace 保持敏感、限本地存储；不得默认记录整个浏览器会话。 |
| P2 | DOCX 作为导出 adapter，不改变 Markdown 主文档 | 若用户将来要求 Word，围绕 Markdown/evidence manifest 做可选 writer，图片按正文位置插入；不得采用当前上游“图片集中在末尾”的关联方式。复用依赖前先解决 auto solver 授权问题。 |
| P3 | 不把全局桌面录制作为默认能力 | 当前 Windows `terminal-run`/按窗口 capture 满足真实截图；需要非浏览器 GUI 全流程时先检测宿主能力，短时、用户启动、可暂停/丢弃并展示 raw-key 风险。不要为了复用记录工具就安装其额外 pynput/mss/uv 环境。 |

## 许可证与可复用状态

| 仓库 | 本次核对 | 对代码复用的处理 |
|---|---|---|
| `not-narleeek/ctf-skills` | 根 `LICENSE`、package.json 均为 MIT | 可以复制/修改代码或文本，但保留版权和许可声明；仍优先只复用流程理念。 |
| `Jiaerhan/auto-ctf-solver` | 无根 `LICENSE`；GitHub license 为 null；`pyproject.toml` 和 README 声称 MIT | 状态不完整。本文只分析，不复制其代码。要复用 writer 源码时先取得权利人明确许可或待上游补齐 LICENSE。 |
| `ugarchance/record-and-replay-skill` | 根 LICENSE 为 MIT | 可按 MIT 条款复用小型代码并保留 copyright/permission notice；该许可证不消除桌面事件隐私和凭证处理风险。 |
| `kriss-045/agent-skills` | 无根 LICENSE/COPYING，GitHub license 为 null | 仅供观察公开的结构，不复制作者档案、例句或 Skill 原文；自行实现同类 Profile 字段。 |
| `lackeyjb/playwright-skill` | 根 LICENSE 与 package.json 为 MIT | 可以复用 helper/runner 代码并保留许可声明；对 StyleForge 而言属于 optional component。 |

StyleForge 新 GitHub 仓库发布时，本次没有替它添加任何许可证；是否开源及采用何种 license 仍属于项目作者的发布选择。

## 依赖与 Windows 适配风险

- **ctf-skills：** 写作模板自身没有运行库；整个 skill collection 的流程假设有 Agent、filesystem、bash/Python 及多个外接 CTF 工具。部分命令用 Bash Unix 工具，不能原样作为 PowerShell 步骤。
- **auto-ctf-solver：** Python >=3.10；Anthropic SDK、Docker 与多种文档/解析库，配置和镜像开销高。其截图路径依赖 Docker/Linux `scrot`/CutyCapt/ImageMagick，和 StyleForge 已有 Windows ImageGrab/Playwright 路径不等价。依赖及许可证不确定性使整包引入优先级低。
- **record-and-replay-skill：** Browser 模式 Node >=18 + Playwright + Chrome/Chromium；Desktop 模式另要 uv、Python 3.12 venv、pynput/mss/Pillow。driver 有 Windows `Scripts/python.exe`、Windows STOP-file 与 native active-window code；Linux 桌面依赖 X11。桌面 source 原始保存 keystrokes，不遮罩；Trace mode full 会增加图像/DOM数据量。项目未在本调研环境安装/运行。
- **agent-skills：** Markdown-only style refs，无执行依赖，但对 StyleForge 不是算法或数据格式的替代品。
- **playwright-skill：** Node >=20、Playwright，setup 需安装 Chromium 或发现本机 Chrome/Edge；Windows runner 采用 Node path/cwd，helper 可显式使用 `PW_CHANNEL=msedge` / `PW_EXECUTABLE_PATH`。不处理 Windows 原生 GUI/终端截图。
- **当前 StyleForge：** 已按 Python skill/CLI 结构运行，依赖见 `requirements.txt`。采纳上游 Browser recorder 会多出 node/npm/Playwright 环境；除非确实需要逐操作事件历史，不要把这条可选依赖升级为核心依赖。

## 后续核验边界

- Git 仓库浅克隆快照及 commit SHA 已写在本报告链接和 `work/reuse-research-20261119/repos/` 中；链接中的行号锚点按当前 pinned commit，不依赖 README 动态版本。
- 本次未执行上游可执行代码或安装上游依赖；源码声明的 self-test、pytest 和 npm test 均没有在本次调研中运行。上游“功能已实现”由静态代码证据判断，运行兼容性未验证。StyleForge 自身 `python -m pytest -q` 已运行并通过 43 条测试。
- Playwright repo 的测试确实区分 unit/mock 与本地浏览器 smoke test；`auto-ctf-solver` 没有找到 writer/screenshot 专项测试；本轮新运行的 StyleForge 隔离 fixture suite 通过 43 条测试。

## 上游固定快照

| 仓库 | HEAD commit | 根许可证状态 | 关键源码入口 |
|---|---|---|---|
| `not-narleeek/ctf-skills` | `08f44e839cb3826e7f4f5376f42591234d430a17` | MIT | `skills/ctf-writeup/SKILL.md`; `scripts/validate-skills.py` |
| `Jiaerhan/auto-ctf-solver` | `a09da7dc2526ed4c38adaefb8c37b464105536fc` | 缺 LICENSE 文件；metadata 声称 MIT | `src/auto_ctf/writeup/{generator,md_writer,docx_writer}.py`; `src/auto_ctf/tools/screenshot.py` |
| `ugarchance/record-and-replay-skill` | `5e6b52ecb097df67eb1c94e83abfd5f39c663ef5` | MIT | `scripts/recorder.mjs`; `scripts/desktop-lite-recorder.py`; `scripts/summarize.mjs` |
| `kriss-045/agent-skills` | `b74b9d7b9dc9534607fe64e7a78fe053a1c0f8a1` | 未声明 | `skills/kriss-writing-style/`; `skills/kriss-article-writer/` |
| `lackeyjb/playwright-skill` | `dd47a6a023e249eb1b36e9e943eab89d0900865d` | MIT | `skills/playwright-skill/run.js`; `lib/helpers.js`; `tests/` |

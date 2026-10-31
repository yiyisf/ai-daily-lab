# 玩具实验：用三条规则拦下绕开组件库的 AI 改动

## 目的

[ponytail](https://github.com/DietrichGebert/ponytail) 技能要求 Agent 写代码前先问一句「代码库里是不是已经有了」，它的 README 举的例子是：要一个日期选择器，没有技能时 Agent 手写整套日历，有技能时直接复用仓库里的 `Input` 组件。

技能靠的是提示词，模型不一定每次都照做。本实验**不是 ponytail 的代码，也不调用任何模型**，只用 Python 标准库写三条确定性规则，在 8 条手写的模拟前端改动上检查「AI 有没有绕开项目已有的组件库」：

- **R1**：用了原生 HTML 元素，而组件库里已有对应封装（如 `<button>` → `Button`、`<dialog>` → `Modal`）
- **R2**：新定义的组件名里包含已有组件名（如 `MyButton`、`CustomDatePicker`），疑似重复造轮子
- **R3**：新增依赖与已有组件功能重叠（如已有 `DatePicker` 又装 `react-datepicker`）

这类规则与模型无关，可以放进 pre-commit、CI 或 Agent 的 Hook 里，作为提示词之外的一道兜底。

## 步骤

```bash
python main.py
```

程序逐条打印每个模拟改动的判定（FLAG / OK）和命中的规则，然后输出 5 项 `[PASS]/[FAIL]` 检查、`METRIC:` 指标和最后一行 `RESULT:`；任何检查失败时以非零状态退出。

## 预期结果

- 手写日历并新装日期库、另写 `MyButton`、用原生 `<dialog>` 写弹窗、用原生 `<select>` 并新装下拉库，这 4 条改动都被拦下
- 复用 `Input`、`Select`、`Button`、`Textarea` 的改动不被误拦
- `<input type="hidden">` 这类不需要走组件库的写法按例外放行

## 局限

- 模拟改动是手写的，数量很少，检出率和误报率只说明规则逻辑，不代表真实项目里的效果
- 规则只看标签名、组件名和依赖名：换个名字、用 `React.createElement`、或者把原生标签藏在另一个文件里，都可能漏掉
- R2 按名字包含关系判断，`CitySelect` 这种基于 `Select` 的合理封装也会被标出，真实使用时需要白名单或人工确认
- 组件库索引在这里是写死的；实际项目可以从 `src/components` 目录或设计系统的导出清单自动生成

## 启示与可以继续尝试

- 把 `LIBRARY` 换成你项目组件库的真实清单，把 `DIFFS` 换成 `git diff` 的新增行，就能对 AI 的改动做一次快速检查
- 规则命中后，把命中的原因（「组件库已有 Button」）回传给 Agent，比单纯在提示词里写「请复用组件」更具体
- 试着加一条规则：内联 `style` 或硬编码颜色值，检查是否绕开了设计令牌

## 内网复现

- 只用 Python 标准库，不需要安装任何依赖，`requirements.txt` 仅作说明
- 程序完全离线运行，不访问网络，也不需要 API key 或 GPU
- 如需试用 ponytail 本身：它是一个 `SKILL.md` 加若干适配文件，内网可先在外网机器下载仓库，再把 `skills/ponytail/SKILL.md` 或 `AGENTS.md` 拷进项目；Claude Code / Codex 的插件市场安装方式需要能访问 GitHub

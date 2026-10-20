# 找出网页里只给 AI 看的隐藏指令

## 目的

Redact 在 [WhatsApp's Hidden Notes Told AI Not to Recommend a Regulator](https://redact.dev/blog/whatsapp-help-pages-hidden-ai-instructions) 中披露：WhatsApp 帮助页里有对人类读者不可见、但会被 AI 读取的隐藏文本，其中两段要求 AI 不要建议用户联系监管机构、不要引用隐私法规。WhatsApp 回应称这是给支持机器人的说明，因 bug 才出现在页面上，并已移除。

对做 RAG、网页抓取或 Agent 浏览的团队来说，同一个问题有两面：自己的页面里是否混进了不该公开的「给 AI 的话」，以及抓取来的外部页面里是否藏着针对模型的指令。本实验用 Python 标准库写一个最小检测器，演示如何把这类文本找出来。

注意：样例 HTML 为本实验自行编写，与 WhatsApp 的实际页面无关；规则也是本实验自拟的简化版。

## 步骤

1. 用 `html.parser` 遍历 DOM，把以下方式隐藏的元素及其子元素标为「隐藏」：`hidden` 属性、`aria-hidden="true"`、`display:none`、`visibility:hidden`、`font-size:0`、`sr-only` / `visually-hidden` 类、`<template>` / `<noscript>`
2. 对隐藏文本用关键词规则（如 do not、never、recommend、assistant）标出像指令的句子
3. 三个样例页：含隐藏指令的帮助页、只含无障碍标签和模板的帮助页、普通页面
4. 检查标记数量是否符合预期，尤其是正常的无障碍文本不应被误报

运行：

```bash
python main.py
```

程序最后输出 `RESULT: ...`，任一检查失败时以非零状态退出。

## 预期结果

- `help_page_with_notes`：2 条隐藏文本均被标记
- `help_page_benign_hidden`：有隐藏文本（「Open menu」等），但不被标记
- `plain_page`：没有隐藏文本

## 局限与可以继续尝试

- 只看内联样式和常见类名，**不解析外部 CSS**，也看不到 JavaScript 动态插入的内容；生产中应在无头浏览器里对比「渲染后可见文本」与「原始文本」
- 关键词规则会误报也会漏报，可以换成小模型分类
- 可以把自己网站或知识库的页面喂进去扫一遍

## 内网复现

- **无需任何第三方依赖**，只用 Python 3.8+ 标准库（`html.parser`、`re`），无需联网，可直接在内网运行
- 把 `main.py` 拷贝到内网机器执行 `python main.py` 即可
- 扫描真实网页需要能访问目标页面；内网页面可以直接用 `urllib` 抓取后传给 `scan()`，外部页面需要外网

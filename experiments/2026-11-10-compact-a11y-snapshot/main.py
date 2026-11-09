"""玩具实验：给没有视觉能力的模型看页面，原始 HTML 和「交互元素快照」差多少。

参考 LangChain 2026-11-03 的浏览器工具对比：Stagehand 的 snapshot 返回裁剪过的
无障碍树，给可交互元素编号，Agent 不需要读原始 HTML 或写选择器。
本实验只用 Python 标准库，在一个内置的后台管理页面上：
  1. 从 HTML 抽取可交互元素，按「角色 + 可访问名称」生成编号快照（平铺版）；
  2. 再给每个元素附上所在区块标题 / 表格行的首列（带上下文版）；
  3. 比较三者体积，并检查按名称定位是否唯一。
不调用模型、不访问网络、不启动浏览器。
"""
import sys
from collections import Counter
from html.parser import HTMLParser

USERS = ["张三", "李四", "王五", "赵六", "孙七", "周八"]

def build_page():
    rows = []
    for i, name in enumerate(USERS, 1):
        rows.append(f"""
      <tr class="row row-{i}" data-id="{1000+i}">
        <td class="cell cell-name"><div class="wrap"><span class="txt">{name}</span></div></td>
        <td class="cell"><div class="wrap"><span class="badge badge-ok" style="padding:2px 6px;border-radius:4px">正常</span></div></td>
        <td class="cell cell-ops"><div class="btn-group">
          <button class="btn btn-sm btn-link" type="button"><svg width="12" height="12" viewBox="0 0 24 24"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25z"/></svg><span>编辑</span></button>
          <button class="btn btn-sm btn-link btn-danger" type="button"><svg width="12" height="12" viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12z"/></svg><span>删除</span></button>
        </div></td>
      </tr>""")
    script = "\n".join(f"  window.__cfg_{i} = {{theme: 'light', locale: 'zh-CN', flags: [{i}, {i*2}, {i*3}]}};" for i in range(60))
    style = "\n".join(f"  .c-{i} {{ margin: {i}px; padding: {i%7}px; color: #{i:06x}; }}" for i in range(80))
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>用户管理</title>
<style>
{style}
</style></head>
<body>
<div id="app" class="layout"><div class="layout-header"><nav class="nav">
  <a href="/home" class="nav-link">首页</a>
  <a href="/users" class="nav-link active">用户管理</a>
  <a href="/settings" class="nav-link">系统设置</a>
</nav></div>
<div class="layout-main"><div class="panel">
  <h2 class="panel-title">筛选</h2>
  <form class="filter-form"><div class="form-row">
    <label for="kw">关键词</label><div class="input-wrap"><input id="kw" type="text" placeholder="请输入姓名"></div>
    <label for="status">状态</label><div class="select-wrap"><select id="status"><option>全部</option><option>正常</option><option>停用</option></select></div>
    <button type="submit" class="btn btn-primary"><span>查询</span></button>
    <button type="reset" class="btn"><span>重置</span></button>
  </div></form>
</div>
<div class="panel">
  <h2 class="panel-title">用户列表</h2>
  <div class="toolbar"><button class="btn btn-primary" type="button"><span>新建用户</span></button></div>
  <table class="table"><thead><tr><th>姓名</th><th>状态</th><th>操作</th></tr></thead><tbody>{''.join(rows)}
  </tbody></table>
  <div class="pager"><button aria-label="上一页" class="btn btn-icon">&lt;</button><button aria-label="下一页" class="btn btn-icon">&gt;</button></div>
</div>
<div class="panel modal" role="dialog">
  <h2 class="panel-title">新建用户</h2>
  <form><label for="new-name">姓名</label><input id="new-name" type="text">
  <label for="new-mail">邮箱</label><input id="new-mail" type="email">
  <button type="button" class="btn"><span>取消</span></button>
  <button type="submit" class="btn btn-primary"><span>保存</span></button></form>
</div></div></div>
<script>
{script}
</script>
</body></html>"""

INTERACTIVE = {"a": "link", "button": "button", "input": "textbox", "select": "combobox", "textarea": "textbox"}
SKIP_TEXT = {"script", "style", "option", "svg", "path"}

class Snapshot(HTMLParser):
    def __init__(self):
        super().__init__()
        self.labels = {}          # for-id -> label text
        self.elements = []        # dicts
        self.stack = []           # open tags
        self.cur = None           # element collecting text
        self.label_for = None
        self.label_text = ""
        self.heading = None
        self.in_heading = False
        self.heading_buf = ""
        self.row_first_cell = None
        self.cell_index = -1
        self.cell_buf = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.stack.append(tag)
        if tag == "h2":
            self.in_heading, self.heading_buf = True, ""
        if tag == "tr":
            self.row_first_cell, self.cell_index = None, -1
        if tag == "td":
            self.cell_index += 1
            self.cell_buf = ""
        if tag == "label":
            self.label_for, self.label_text = a.get("for"), ""
        if tag in INTERACTIVE:
            el = {"role": INTERACTIVE[tag], "id": a.get("id"), "aria": a.get("aria-label"),
                  "placeholder": a.get("placeholder"), "text": "",
                  "section": self.heading, "row": self.row_first_cell}
            self.elements.append(el)
            if tag in ("a", "button"):
                self.cur = el

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "h2":
            self.in_heading = False
            self.heading = self.heading_buf.strip()
        if tag == "td" and self.cell_index == 0:
            self.row_first_cell = self.cell_buf.strip()
        if tag == "label" and self.label_for:
            self.labels[self.label_for] = self.label_text.strip()
            self.label_for = None
        if tag in ("a", "button"):
            self.cur = None
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()

    def handle_data(self, data):
        if any(t in SKIP_TEXT for t in self.stack):
            return
        if self.in_heading:
            self.heading_buf += data
        if self.cell_index == 0 and "td" in self.stack:
            self.cell_buf += data
        if self.label_for is not None:
            self.label_text += data
        if self.cur is not None:
            self.cur["text"] += data

def accessible_name(el, labels):
    for cand in (el["aria"], labels.get(el["id"]) if el["id"] else None, el["text"].strip(), el["placeholder"]):
        if cand and cand.strip():
            return cand.strip()
    return ""

def render(elements, labels, with_context):
    lines = []
    for i, el in enumerate(elements, 1):
        name = accessible_name(el, labels)
        line = f'[e{i}] {el["role"]} "{name}"'
        if with_context:
            ctx = [c for c in (el["section"], el["row"]) if c]
            if ctx:
                line += " @ " + " / ".join(ctx)
        lines.append(line)
    return lines

def key_of(line):
    return line.split("] ", 1)[1]

def main():
    html = build_page()
    p = Snapshot()
    p.feed(html)
    flat = render(p.elements, p.labels, with_context=False)
    ctx = render(p.elements, p.labels, with_context=True)
    flat_txt, ctx_txt = "\n".join(flat), "\n".join(ctx)

    print("== 带上下文的快照（前 12 行）==")
    for line in ctx[:12]:
        print("  " + line)
    print(f"  ...（共 {len(ctx)} 行）")

    flat_dup = {k: n for k, n in Counter(map(key_of, flat)).items() if n > 1}
    ctx_dup = {k: n for k, n in Counter(map(key_of, ctx)).items() if n > 1}
    print("\n平铺快照里重名的元素：", ", ".join(f"{k}×{n}" for k, n in flat_dup.items()))

    target = [l for l in ctx if '"删除"' in l and "李四" in l]
    target_flat = [l for l in flat if '"删除"' in l]
    print("任务「删除用户 李四」在带上下文快照中匹配：", target)

    raw, f, c = len(html), len(flat_txt), len(ctx_txt)
    print(f"\nMETRIC: 原始 HTML = {raw} 字符")
    print(f"METRIC: 平铺快照 = {f} 字符")
    print(f"METRIC: 带上下文快照 = {c} 字符")
    print(f"METRIC: 带上下文快照占原始 HTML = {100*c/raw:.1f} %")
    print(f"METRIC: 可交互元素 = {len(p.elements)} 个")
    print(f"METRIC: 平铺快照中「删除」候选 = {len(target_flat)} 个")
    print(f"METRIC: 带上下文快照中「删除 李四」候选 = {len(target)} 个")

    unnamed = [l for l in flat if l.endswith('""')]
    checks = [
        (not unnamed, f"每个可交互元素都有可访问名称（无名元素 {len(unnamed)} 个）"),
        (c < raw * 0.25, "带上下文快照不到原始 HTML 的 25%"),
        (len(flat_dup) > 0, "平铺快照存在重名元素，只靠名称无法唯一定位"),
        (not ctx_dup, "附上区块标题和行首列后，所有元素都能唯一区分"),
        (len(target) == 1, "「删除用户 李四」只对应一个编号"),
    ]
    ok = True
    for passed, desc in checks:
        print(("[PASS] " if passed else "[FAIL] ") + desc)
        ok &= passed
    print(f"RESULT: 快照只有原始 HTML 的 {100*c/raw:.1f}%；平铺快照有 {len(flat_dup)} 组重名，附上所在区块和行首列后可唯一定位")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()

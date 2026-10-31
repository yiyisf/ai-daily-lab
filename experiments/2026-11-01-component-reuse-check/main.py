# 仅使用 Python 标准库，无需安装依赖
"""玩具实验：在 AI 生成的前端改动里，找出「绕开项目已有组件库」的写法。

思路来自 ponytail 技能的「先问：代码库里是不是已经有了」这一步，但这里不调用任何模型，
只用三条确定性规则检查手写的模拟改动（diff 的新增部分）：

  规则 R1：用了原生 HTML 元素，而组件库里已有对应封装（如 <button> -> Button）
  规则 R2：新定义的组件名里包含已有组件名（如 MyButton、CustomModal），疑似重复造轮子
  规则 R3：新增的依赖与已有组件功能重叠（如已有 DatePicker 又装 react-datepicker）

每条模拟改动都有人工标注的「应不应该被拦」，程序据此统计检出率和误报。
"""
import re
import sys

# ---- 模拟的项目组件库（相当于 src/components/ui 的索引）----
LIBRARY = {
    "Button": {"wraps": ["button"], "keywords": ["button"]},
    "Input": {"wraps": ["input"], "keywords": ["input"]},
    "Select": {"wraps": ["select"], "keywords": ["select", "dropdown"]},
    "Textarea": {"wraps": ["textarea"], "keywords": ["textarea"]},
    "Modal": {"wraps": ["dialog"], "keywords": ["modal", "dialog"]},
    "DatePicker": {"wraps": [], "keywords": ["datepicker", "date-picker", "calendar"]},
}

# 原生元素的合理例外：这些写法不需要走组件库
ALLOWED_RAW = [
    re.compile(r"<input[^>]*type=[\"']hidden[\"']", re.I),
]

# 只匹配小写开头的原生标签；<Input> 这类大写开头的是组件，不算
RAW_TAG = re.compile(r"<\s*([a-z][a-z0-9]*)\b")
COMPONENT_DEF = re.compile(
    r"(?:function|const|class)\s+([A-Z][A-Za-z0-9]*)\s*(?:=|\(|extends|\{)"
)
DEP_LINE = re.compile(r"^\s*\"([@a-z0-9/._-]+)\"\s*:\s*\"[\^~]?\d", re.I)


def check_diff(diff):
    """返回发现的问题列表，每个问题是 (规则, 说明)。"""
    findings = []
    for line in diff["added"].splitlines():
        if any(p.search(line) for p in ALLOWED_RAW):
            continue
        for tag in RAW_TAG.findall(line):
            tag = tag.lower()
            for comp, meta in LIBRARY.items():
                if tag in meta["wraps"]:
                    findings.append(("R1", f"原生 <{tag}>，组件库已有 {comp}"))
        for name in COMPONENT_DEF.findall(line):
            for comp in LIBRARY:
                if comp.lower() in name.lower() and name != comp:
                    findings.append(("R2", f"新组件 {name} 与已有 {comp} 重名"))
    for line in diff.get("package_json", "").splitlines():
        m = DEP_LINE.match(line)
        if not m:
            continue
        dep = m.group(1).lower()
        for comp, meta in LIBRARY.items():
            if any(k in dep for k in meta["keywords"]):
                findings.append(("R3", f"新依赖 {dep} 与已有 {comp} 重叠"))
    return findings


# ---- 手写的模拟改动：should_flag 为人工标注 ----
DIFFS = [
    {
        "name": "日期选择：手写日历 + 新装依赖",
        "should_flag": True,
        "added": """
import ReactDatePicker from 'react-datepicker'
export function CustomDatePicker({ value, onChange }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="dp">
      <input value={value} onFocus={() => setOpen(true)} readOnly />
      {open && <ReactDatePicker selected={value} onChange={onChange} inline />}
      <button onClick={() => setOpen(false)}>关闭</button>
    </div>
  )
}
""",
        "package_json": '    "react-datepicker": "^7.5.0",',
    },
    {
        "name": "日期选择：复用已有 Input",
        "should_flag": False,
        "added": """
import { Input } from '@/components/ui/input'
export function BirthdayField({ value, onChange }) {
  return <Input type="date" value={value} onChange={onChange} />
}
""",
    },
    {
        "name": "提交按钮：另写一个 MyButton",
        "should_flag": True,
        "added": """
const MyButton = ({ children, ...rest }) => (
  <button className="px-4 py-2 rounded bg-blue-600 text-white" {...rest}>{children}</button>
)
""",
    },
    {
        "name": "确认弹窗：用原生 dialog 自己写",
        "should_flag": True,
        "added": """
export function ConfirmDelete({ open, onOk }) {
  return (
    <dialog open={open} className="confirm">
      <p>确定删除吗？</p>
      <Button onClick={onOk}>确定</Button>
    </dialog>
  )
}
""",
    },
    {
        "name": "筛选表单：复用 Select 与 Button，带隐藏字段",
        "should_flag": False,
        "added": """
import { Select } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
export function StatusFilter({ form }) {
  return (
    <form>
      <input type="hidden" name="page" value="1" />
      <Select name="status" options={STATUS_OPTIONS} />
      <Button type="submit">筛选</Button>
    </form>
  )
}
""",
    },
    {
        "name": "下拉框：原生 select + 新装下拉库",
        "should_flag": True,
        "added": """
export function CitySelect({ cities }) {
  return <select name="city">{cities.map(c => <option key={c}>{c}</option>)}</select>
}
""",
        "package_json": '    "react-select": "^5.10.0",',
    },
    {
        "name": "备注输入：复用 Textarea",
        "should_flag": False,
        "added": """
import { Textarea } from '@/components/ui/textarea'
export function RemarkField(props) {
  return <Textarea rows={4} maxLength={200} {...props} />
}
""",
    },
    {
        "name": "工具函数：与组件无关",
        "should_flag": False,
        "added": """
export function formatAmount(cents) {
  return (cents / 100).toFixed(2)
}
""",
    },
]


def main():
    tp = fp = fn = tn = 0
    rule_hits = {"R1": 0, "R2": 0, "R3": 0}
    for d in DIFFS:
        findings = check_diff(d)
        flagged = bool(findings)
        for rule, _ in findings:
            rule_hits[rule] += 1
        print(f"--- {d['name']}  -> {'FLAG' if flagged else 'OK'}")
        for rule, msg in findings:
            print(f"    {rule}: {msg}")
        if flagged and d["should_flag"]:
            tp += 1
        elif flagged and not d["should_flag"]:
            fp += 1
        elif not flagged and d["should_flag"]:
            fn += 1
        else:
            tn += 1

    positives = tp + fn
    recall = 100.0 * tp / positives if positives else 0.0
    false_alarm = 100.0 * fp / (fp + tn) if (fp + tn) else 0.0

    checks = [
        (tp == positives, f"应拦的 {positives} 条改动全部被至少一条规则拦下"),
        (fp == 0, "复用组件库的改动没有被误拦"),
        (not check_diff(DIFFS[4]), "type=hidden 的原生 input 按例外放行"),
        (any(r == "R3" for r, _ in check_diff(DIFFS[0])), "新装的日期库被 R3 识别为与 DatePicker 重叠"),
        (any(r == "R2" for r, _ in check_diff(DIFFS[2])), "MyButton 被 R2 识别为与 Button 重名"),
    ]
    print()
    ok = True
    for passed, desc in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {desc}")
        ok = ok and passed

    print(f"METRIC: 检出率 = {recall:.1f} %")
    print(f"METRIC: 误报率 = {false_alarm:.1f} %")
    for rule in ("R1", "R2", "R3"):
        print(f"METRIC: {rule} 命中次数 = {rule_hits[rule]} 次")

    if ok:
        print(f"RESULT: 三条确定性规则在 {len(DIFFS)} 条模拟改动上拦下全部 {positives} 条绕开组件库的写法，无误报；规则只认名字和标签，换个写法就可能漏")
    else:
        print("RESULT: 有检查未通过，规则需要调整")
        sys.exit(1)


if __name__ == "__main__":
    main()

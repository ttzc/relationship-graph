"""
audit_graph.py 回归测试
=======================

stdlib unittest + tempfile 构造迷你 vault fixture，覆盖易误报/漏报的关键解析路径。
运行：python -m unittest test_audit_graph -v   （需要 pyyaml）
"""

import datetime
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_graph as ag  # noqa: E402

TODAY = datetime.date(2026, 11, 23)


def contact_yaml(nickname="甲", platform_block='  qq: "10001"', strength="密友",
                 last_contact="2026-11-20", extra_top=""):
    return f"""---
title: {nickname}
type: contact
---

# {nickname}

```yaml
nickname: "{nickname}"
platform:
{platform_block}
identity: "测试身份"
met: "测试认识途径"
strength: "{strength}"
last_contact: "{last_contact}"
{extra_top}```

## 可帮事项（AI 联想的核心）

- 测试

## 触发标签

[[S1]]

## 历史互动

- 无

## 备注

- 无
"""


def index_md(overview_rows, roster_rows, search_col=True, tags_rows=None):
    cols = "| 昵称 | 缩写 | 身份 | 触发标签 | 强度 | 最近联系 | 链接 |" if search_col \
        else "| 昵称 | 身份 | 触发标签 | 强度 | 最近联系 | 链接 |"
    sep = "| --- | --- | --- | --- | --- | --- | --- |" if search_col \
        else "| --- | --- | --- | --- | --- | --- |"
    roster_md = "\n".join(
        f"| {name} | 场景 | {count} | [[{name}]] |" for name, count in roster_rows)
    tags_md = ""
    if tags_rows:
        rows = "\n".join(f"| {name} | 场景 | [[{name}]] |" for name in tags_rows)
        tags_md = f"## 按标签检索\n\n### 学校\n\n| 学校 | 触发场景 | 标签文件 |\n| --- | --- | --- |\n{rows}\n"
    return f"""---
title: 索引
type: index
---

# 索引

## 联系人总览

{cols}
{sep}
{os.linesep.join(overview_rows)}

## 名单

| 名单 | 触发场景 | 已登记/仅名单 | 链接 |
| --- | --- | --- | --- |
{roster_md}

{tags_md}"""


def roster_md(members_lines, heading="## 成员", header="| 姓名 | 角色 | 状态 |",
              sep="| --- | --- | --- |", extra_sections=""):
    return f"""# 名单甲

**触发场景**：测试

{heading}

{header}
{sep}
{os.linesep.join(members_lines)}
{extra_sections}"""


def tag_md(name, members=None, heading="## 相关联系人"):
    body = f"{heading}\n" + "\n".join(members) if members is not None else ""
    return f"""---
title: {name}
type: school
---

# {name}

**触发场景**：测试

{body}
"""


class VaultCase(unittest.TestCase):
    """构造/销毁迷你 vault 的基类。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="rg_audit_test_")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, rel, content):
        path = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def result(self, stale_days=90, today=TODAY):
        return ag.run_audit(self.dir, stale_days=stale_days, today=today)

    def msgs(self, issues, category=None, severity=None):
        return [i["message"] for i in issues.detail
                if (category is None or i["category"] == category)
                and (severity is None or i["severity"] == severity)]

    def baseline(self, search_col=True):
        """健康 vault：2 联系人、2 标签（含成员列表）、1 名单、一致 INDEX。"""
        self.write("contacts/甲.md", contact_yaml("甲"))
        self.write("contacts/乙.md", contact_yaml("乙", platform_block='  qq: "10002"')
                   .replace("[[S1]]", "[[S2]]"))
        self.write("tags/school/S1.md", tag_md("S1", ["- [[甲]] — 测试身份"]))
        self.write("tags/school/S2.md", tag_md("S2", ["- [[乙]] — 测试身份"]))
        self.write("rosters/R1.md", roster_md(
            ["| [[甲]] | 同学 | 已登记 |", "| 路人 | 同学 | 仅名单 |"]))
        self.write("INDEX.md", index_md(
            ["| 甲 | jia | 测试身份 | [[S1]] | 密友 | 2026-11-20 | [[甲]] |",
             "| 乙 | | 测试身份 | [[S2]] | 密友 | 2026-11-20 | [[乙]] |"],
            [("R1", "1 已登记 / 1 仅名单")],
            search_col=search_col,
            tags_rows=["S1", "S2"]))


class TestBaseline(VaultCase):
    def test_healthy_vault_zero_errors(self):
        self.baseline()
        r = self.result()
        self.assertEqual(r["issues"].count(severity=ag.ERR), 0,
                         msg="\n".join(r["issues"].errors()))
        self.assertEqual(r["issues"].count(severity=ag.HINT), 0,
                         msg="\n".join(r["issues"].hints()))

    def test_six_column_index_ok(self):
        """6 列（无检索列）表头按列名映射，不应产生坏行。"""
        self.write("contacts/甲.md", contact_yaml("甲"))
        self.write("contacts/乙.md", contact_yaml("乙", platform_block='  qq: "10002"')
                   .replace("[[S1]]", "[[S2]]"))
        self.write("tags/school/S1.md", tag_md("S1", ["- [[甲]] — 测试身份"]))
        self.write("tags/school/S2.md", tag_md("S2", ["- [[乙]] — 测试身份"]))
        self.write("rosters/R1.md", roster_md(
            ["| [[甲]] | 同学 | 已登记 |", "| 路人 | 同学 | 仅名单 |"]))
        self.write("INDEX.md", index_md(
            ["| 甲 | 身份 | [[S1]] | 密友 | 2026-11-20 | [[甲]] |",
             "| 乙 | 身份 | [[S2]] | 密友 | 2026-11-20 | [[乙]] |"],
            [("R1", "1 已登记 / 1 仅名单")],
            search_col=False, tags_rows=["S1", "S2"]))
        r = self.result()
        self.assertEqual(r["issues"].count(severity=ag.ERR), 0,
                         msg="\n".join(r["issues"].errors()))


class TestIndexReconciliation(VaultCase):
    def test_merged_row_detected(self):
        """真实坏例形态：两行用 `]] || ` 误并成一行 → 坏行 + 两行缺账。"""
        self.baseline()
        self.write("INDEX.md", index_md(
            ["| 甲 | jia | 身份 | [[S1]] | 密友 | 2026-11-20 | [[甲]] || 乙 | x | 身份 | [[S2]] | 密友 | 2026-11-20 | [[乙]] |"],
            [("R1", "1 已登记 / 1 仅名单")],
            tags_rows=["S1", "S2"]))
        r = self.result()
        malformed = r["index"]["malformed_rows"]
        self.assertEqual(len(malformed), 1)
        self.assertEqual(malformed[0]["cells"], 15)
        self.assertEqual(set(r["index"]["missing_contacts"]), {"甲", "乙"})

    def test_roster_count_drift(self):
        """真实坏例形态：INDEX 计数落后于名单文件（升级成员未同步）。"""
        self.baseline()
        self.write("INDEX.md", index_md(
            ["| 甲 | jia | 身份 | [[S1]] | 密友 | 2026-11-20 | [[甲]] |",
             "| 乙 | | 身份 | [[S2]] | 密友 | 2026-11-20 | [[乙]] |"],
            [("R1", "3 已登记 / 0 仅名单")],
            tags_rows=["S1", "S2"]))
        r = self.result()
        self.assertEqual(len(self.msgs(r["issues"], "索引", ag.ERR)), 1)
        self.assertIn("计数过期", self.msgs(r["issues"], "索引", ag.ERR)[0])

    def test_legacy_plus_format_and_self_cell(self):
        """旧 `N + M` 计数兼容；「4 已登记（成员 5 人，含本人）」式计数格匹配不报错。"""
        self.write("contacts/甲.md", contact_yaml("甲"))
        self.write("tags/school/S1.md", tag_md("S1", ["- [[甲]] — 测试"]))
        self.write("rosters/R1.md", roster_md(
            ["| [[甲]] | 同学 | 已登记 |", "| 路人 | 同学 | 仅名单 |"]))
        self.write("rosters/R2.md", roster_md(
            ["| [[甲]] | 负责人 | 已登记 |"],
            heading="## 项目成员（2 人 · 与申报书一致）",
            header="| 姓名 | 角色 | 状态 | 学号 |", sep="| --- | --- | --- | --- |"))
        self.write("INDEX.md", index_md(
            ["| 甲 | jia | 身份 | [[S1]] | 密友 | 2026-11-20 | [[甲]] |"],
            [("R1", "1 + 1"), ("R2", "1 已登记（成员 2 人，含本人）")],
            tags_rows=["S1"]))
        r = self.result()
        self.assertEqual(r["issues"].count("索引", ag.ERR), 0,
                         msg="\n".join(r["issues"].errors()))

    def test_pseudo_tag_and_search_column_hints(self):
        self.baseline()
        self.write("INDEX.md", index_md(
            ["| 甲 | jia justice | 身份 | S1/S2 | 密友 | 2026-11-20 | [[甲]] |",
             "| 乙 | | 身份 | [[S2]] | 密友 | 2026-11-20 | [[乙]] |"],
            [("R1", "1 已登记 / 1 仅名单")],
            tags_rows=["S1", "S2"]))
        r = self.result()
        self.assertEqual(len(r["index"]["pseudo_tag_rows"]), 1)
        # 甲有 justice 昵称值但检索列写法核对：cell 含 justice 不报；构造缺值场景
        self.assertEqual(r["index"]["search_cell_missing"], [])
        self.write("INDEX.md", index_md(
            ["| 甲 | jia | 身份 | [[S1]] | 密友 | 2026-11-20 | [[甲]] |",
             "| 乙 | | 身份 | [[S2]] | 密友 | 2026-11-20 | [[乙]] |"],
            [("R1", "1 已登记 / 1 仅名单")],
            tags_rows=["S1", "S2"]))
        self.write("contacts/甲.md", contact_yaml("甲", extra_top='qq_nickname: "justice"\n'))
        r = self.result()
        self.assertEqual(len(r["index"]["search_cell_missing"]), 1)


    def test_tag_cell_drift_vs_contact_tags(self):
        """档案挂了真实标签、INDEX 触发标签格没同步 → 提示级漂移（不判失败）。"""
        self.baseline()
        # 甲档案追加 [[S2]]（S2 是真实标签文件），但 INDEX 甲行只列 [[S1]]
        self.write("contacts/甲.md", contact_yaml("甲").replace(
            "## 触发标签\n\n[[S1]]", "## 触发标签\n\n[[S1]] [[S2]]"))
        # 标签页 S2 也补上甲，避免反向漂移错误干扰
        self.write("tags/school/S2.md", tag_md(
            "S2", ["- [[乙]] — 测试身份", "- [[甲]] — 测试身份"]))
        r = self.result()
        self.assertEqual(r["issues"].count(severity=ag.ERR), 0,
                         msg="\n".join(r["issues"].errors()))
        self.assertEqual(len(r["index"]["tag_cell_drift"]), 1)
        drift = r["index"]["tag_cell_drift"][0]
        self.assertEqual(drift["contact"], "甲")
        self.assertIn("S2", drift["missing"])
        self.assertTrue(any("触发标签格落后于档案" in m
                            for m in self.msgs(r["issues"], severity=ag.HINT)))
        # 同步 INDEX 格后漂移消失
        self.write("INDEX.md", index_md(
            ["| 甲 | jia | 身份 | [[S1]] [[S2]] | 密友 | 2026-11-20 | [[甲]] |",
             "| 乙 | | 身份 | [[S2]] | 密友 | 2026-11-20 | [[乙]] |"],
            [("R1", "1 已登记 / 1 仅名单")],
            tags_rows=["S1", "S2"]))
        r = self.result()
        self.assertEqual(len(r["index"]["tag_cell_drift"]), 0)


class TestRosters(VaultCase):
    def test_heading_decoys_not_parsed(self):
        """`## 分工线（…成员介绍…）`、`## 指导教师`、`## 队籍判定规则` 不得被当成员节。"""
        self.write("contacts/甲.md", contact_yaml("甲"))
        self.write("contacts/徐老师.md", contact_yaml("徐老师", platform_block='  qq: "10002"'))
        self.write("tags/school/S1.md", tag_md("S1", ["- [[甲]] — 测试"]))
        self.write("rosters/R1.md", roster_md(
            ["| [[甲]] | 成员 | 已登记 |"],
            heading="## 项目成员（1 人 · 定稿）",
            extra_sections="""
## 指导教师

| 姓名 | 身份 | 工号 |
| --- | --- | --- |
| [[徐老师]] | 第一指导教师 | 123 |

## 分工线（申报书「团队主要成员介绍」口径）

| 线 | 人 | 做什么 |
|---|---|---|
| AI | 甲 | 架构 |

## 队籍判定规则

| 成绩 | 队籍 |
|---|---|
| 金牌 | 正式 |
"""))
        self.write("INDEX.md", index_md(
            ["| 甲 | jia | 身份 | [[S1]] | 密友 | 2026-11-20 | [[甲]] |",
             "| 徐老师 | xs | 教师 | [[S1]] | 师生 | 2026-11-20 | [[徐老师]] |"],
            [("R1", "1 已登记 / 0 仅名单")],
            tags_rows=["S1"]))
        self.write("tags/school/S1.md", tag_md("S1", ["- [[甲]] — 测试", "- [[徐老师]] — 教师"]))
        r = self.result()
        self.assertEqual(len(r["rosters"]["R1"]["members"]), 1)
        self.assertEqual(r["issues"].count(severity=ag.ERR), 0,
                         msg="\n".join(r["issues"].errors()))

    def test_generic_heading_before_paren(self):
        """规则是「首个括号前含成员」：## 主要成员 也算成员节，不再硬编码「项目」。"""
        self.write("contacts/甲.md", contact_yaml("甲"))
        self.write("tags/school/S1.md", tag_md("S1", ["- [[甲]] — 测试"]))
        self.write("rosters/R1.md", roster_md(
            ["| [[甲]] | 成员 | 已登记 |"], heading="## 主要成员"))
        self.write("INDEX.md", index_md(
            ["| 甲 | jia | 身份 | [[S1]] | 密友 | 2026-11-20 | [[甲]] |"],
            [("R1", "1 已登记 / 0 仅名单")], tags_rows=["S1"]))
        r = self.result()
        self.assertTrue(r["rosters"]["R1"]["has_member_section"])
        self.assertEqual(len(r["rosters"]["R1"]["members"]), 1)
        self.assertEqual(r["issues"].count(severity=ag.ERR), 0,
                         msg="\n".join(r["issues"].errors()))

    def test_decoy_only_roster_reports_hint(self):
        """只有诱饵标题（成员在括号内/无成员节）→ 解析不到成员节，给提示不静默。"""
        self.write("contacts/甲.md", contact_yaml("甲"))
        self.write("tags/school/S1.md", tag_md("S1", ["- [[甲]] — 测试"]))
        self.write("rosters/R1.md", roster_md(
            ["| 某人 | 介绍 | 说明 |"],
            heading="## 分工线（申报书「团队主要成员介绍」口径）"))
        self.write("INDEX.md", index_md(
            ["| 甲 | jia | 身份 | [[S1]] | 密友 | 2026-11-20 | [[甲]] |"],
            [("R1", "0 已登记 / 0 仅名单")], tags_rows=["S1"]))
        r = self.result()
        self.assertFalse(r["rosters"]["R1"]["has_member_section"])
        self.assertEqual(r["rosters"]["R1"]["members"], [])
        self.assertTrue(any("成员节" in m for m in r["issues"].hints()))
        self.assertEqual(r["issues"].count("名单", ag.ERR), 0)

    def test_wide_table_status_and_self_row(self):
        """8 列表格右起扫描 + 状态=本人规范形（纯文本、无双链、不入计数）。"""
        self.write("contacts/甲.md", contact_yaml("甲"))
        self.write("tags/school/S1.md", tag_md("S1", ["- [[甲]] — 测试"]))
        self.write("rosters/R1.md", roster_md(
            ["| 房某人（本人） | **负责人**｜AI 线 | 本人 | **123** | 456 | 学院 | 138 | a@b.c |",
             "| [[甲]] | 成员 | 已登记 | **789** | 456 | 学院 | 139 | d@e.f |"],
            header="| 姓名 | 角色 | 状态 | 学号 | 班号 | 学院 | 手机 | 邮箱 |",
            sep="| --- | --- | --- | --- | --- | --- | --- | --- |"))
        self.write("INDEX.md", index_md(
            ["| 甲 | jia | 身份 | [[S1]] | 密友 | 2026-11-20 | [[甲]] |"],
            [("R1", "1 已登记（成员 2 人，含本人）")],
            tags_rows=["S1"]))
        r = self.result()
        counts = ag.roster_stat_counts(r["rosters"]["R1"]["members"])
        self.assertEqual(counts, {"registered": 1, "roster_only": 0, "self": 1, "invalid": 0})
        self.assertEqual(r["issues"].count(severity=ag.ERR), 0,
                         msg="\n".join(r["issues"].errors()))

    def test_self_role_marker_hint_and_self_with_link_error(self):
        self.write("contacts/甲.md", contact_yaml("甲"))
        self.write("tags/school/S1.md", tag_md("S1", ["- [[甲]] — 测试"]))
        self.write("rosters/R1.md", roster_md(
            ["| 房某人 | 学生（本人） | 仅名单 |", "| [[甲]] | 同学 | 已登记 |"]))
        self.write("rosters/R2.md", roster_md(
            ["| [[甲]] | 负责人 | 本人 |"]))
        self.write("INDEX.md", index_md(
            ["| 甲 | jia | 身份 | [[S1]] | 密友 | 2026-11-20 | [[甲]] |"],
            [("R1", "1 已登记 / 1 仅名单"), ("R2", "0 已登记（成员 1 人，含本人）")],
            tags_rows=["S1"]))
        r = self.result()
        self.assertEqual(len(self.msgs(r["issues"], "提示", ag.HINT)), 1)  # 仅 R1 触发自编码统一提示
        self.assertEqual(len(self.msgs(r["issues"], "名单", ag.ERR)), 1)   # 本人行带双链
        self.assertIn("本人」行不应带", self.msgs(r["issues"], "名单", ag.ERR)[0])


class TestMembership(VaultCase):
    def test_forward_and_reverse(self):
        """正向：乙挂 S1 但页没列；反向：丙被页列了但没挂 S1。"""
        self.write("contacts/甲.md", contact_yaml("甲"))
        self.write("contacts/乙.md", contact_yaml("乙", platform_block='  qq: "10002"'))
        self.write("contacts/丙.md",
                   contact_yaml("丙", platform_block='  qq: "10003"')
                   .replace("[[S1]]", "（暂无）"))
        self.write("tags/school/S1.md",
                   tag_md("S1", ["- [[甲]] — 测试", "- [[丙]] — 误列"]))
        self.write("INDEX.md", index_md(
            ["| 甲 | jia | 身份 | [[S1]] | 密友 | 2026-11-20 | [[甲]] |",
             "| 乙 | yi | 身份 | [[S1]] | 密友 | 2026-11-20 | [[乙]] |",
             "| 丙 | bing | 身份 | [[S1]] | 密友 | 2026-11-20 | [[丙]] |"],
            [], tags_rows=["S1"]))
        r = self.result()
        self.assertEqual({p["contact"] for p in r["membership"]["missing"]}, {"乙"})
        rev = {(p["tag"], p["name"], p["reason"]) for p in r["membership"]["reverse"]}
        self.assertEqual(rev, {("S1", "丙", "未挂此标签")})
        # 丙的 INDEX 触发标签列写了 [[S1]] 但档案小节是（暂无）——INDEX 链接可解析，不算断链
        self.assertEqual(len(self.msgs(r["issues"], "断链", ag.ERR)), 0)

    def test_plain_contact_counted_and_wikify_hint(self):
        self.write("contacts/甲.md", contact_yaml("甲"))
        self.write("tags/school/S1.md", tag_md("S1", ["- 甲 — 测试身份"]))
        self.write("INDEX.md", index_md(
            ["| 甲 | jia | 身份 | [[S1]] | 密友 | 2026-11-20 | [[甲]] |"],
            [], tags_rows=["S1"]))
        r = self.result()
        self.assertEqual(r["membership"]["missing"], [])
        self.assertEqual(len(r["membership"]["plain_text"]), 1)
        self.assertIn("建议改为 [[甲]]", "\n".join(r["issues"].hints()))

    def test_hub_page_skipped(self):
        """无联系人节的 hub 型标签页：跳过，不算任何 issue。"""
        self.write("contacts/甲.md", contact_yaml("甲"))
        self.write("tags/school/S1.md",
                   "# S1\n\n## 一、找谁问什么\n\n| 需求 | 找谁 |\n|---|---|\n| 组队 | [[甲]] |\n")
        self.write("INDEX.md", index_md(
            ["| 甲 | jia | 身份 | [[S1]] | 密友 | 2026-11-20 | [[甲]] |"],
            [], tags_rows=["S1"]))
        r = self.result()
        self.assertIn("S1", r["membership"]["skipped_tags"])
        self.assertEqual(r["issues"].count("标签页", ag.ERR), 0)
        self.assertEqual(r["issues"].count("标签页", ag.HINT), 0)


class TestSchemaCollisionsLastContact(VaultCase):
    def test_nested_quote_yaml_surfaces(self):
        bad = contact_yaml("甲").replace(
            'strength: "密友"', 'strength: "熟人（已约，"口头禅"）"')
        self.write("contacts/甲.md", bad)
        self.write("tags/school/S1.md", tag_md("S1", ["- [[甲]] — 测试"]))
        self.write("INDEX.md", index_md(
            ["| 甲 | jia | 身份 | [[S1]] | 密友 | 2026-11-20 | [[甲]] |"],
            [], tags_rows=["S1"]))
        r = self.result()
        self.assertEqual(len(r["schema"]["yaml_errors"]), 1)
        self.assertEqual(len(self.msgs(r["issues"], "schema", ag.ERR)), 1)
        self.assertIn("解析失败", self.msgs(r["issues"], "schema", ag.ERR)[0])
        # 坏块不产生误导性 last_contact 提示
        self.assertEqual(self.msgs(r["issues"], "提示", ag.HINT),
                         [m for m in r["issues"].hints() if "last_contact" not in m])

    def test_unknown_key_hints(self):
        """非规范顶层键（含任何自创名）一律杂键提示；不存在旧键特殊通道。"""
        text = contact_yaml("甲").replace("platform:", "platforms:").replace(
            'met: "测试认识途径"', 'context: "测试认识途径"')
        text = text.replace('last_contact: "2026-11-20"',
                            'qq_nickname: "justice"\nlast_contact: "2026-11-20"')
        self.write("contacts/甲.md", text)
        self.write("tags/school/S1.md", tag_md("S1", ["- [[甲]] — 测试"]))
        self.write("INDEX.md", index_md(
            ["| 甲 | justice | 身份 | [[S1]] | 密友 | 2026-11-20 | [[甲]] |"],
            [], tags_rows=["S1"]))
        r = self.result()
        self.assertNotIn("legacy_keys", r["schema"])
        unknown = {x["key"] for x in r["schema"]["unknown_keys"]}
        self.assertEqual(unknown, {"platforms", "context", "qq_nickname"})
        # platforms 改名后 platform 子键读不到——昵称/碰撞等读取只认规范键
        self.assertEqual(r["collisions"], [])

    def test_collision_vs_crosskey_noncollision(self):
        a = contact_yaml("甲", platform_block='  qq: "10001"\n  email: "10001@qq.com"')
        b = contact_yaml("乙", platform_block='  qq: "10001"').replace("[[S1]]", "[[S1]]")
        self.write("contacts/甲.md", a)
        self.write("contacts/乙.md", b)
        self.write("tags/school/S1.md", tag_md("S1", ["- [[甲]] — 测试", "- [[乙]] — 测试"]))
        self.write("INDEX.md", index_md(
            ["| 甲 | jia | 身份 | [[S1]] | 密友 | 2026-11-20 | [[甲]] |",
             "| 乙 | yi | 身份 | [[S1]] | 密友 | 2026-11-20 | [[乙]] |"],
            [], tags_rows=["S1"]))
        r = self.result()
        self.assertEqual(len(r["collisions"]), 1)
        self.assertEqual(r["collisions"][0]["key"], "qq")
        # 同文件 email 数字与 qq 相同不算第二条

    def test_annotated_qq_still_collides(self):
        a = contact_yaml("甲", platform_block='  qq: "10001（QQ 昵称：X）"')
        b = contact_yaml("乙", platform_block='  qq: "10001"')
        self.write("contacts/甲.md", a)
        self.write("contacts/乙.md", b)
        self.write("tags/school/S1.md", tag_md("S1", ["- [[甲]] — 测试", "- [[乙]] — 测试"]))
        self.write("INDEX.md", index_md(
            ["| 甲 | jia X | 身份 | [[S1]] | 密友 | 2026-11-20 | [[甲]] |",
             "| 乙 | yi | 身份 | [[S1]] | 密友 | 2026-11-20 | [[乙]] |"],
            [], tags_rows=["S1"]))
        r = self.result()
        self.assertEqual(len(r["collisions"]), 1)

    def test_last_contact_variants(self):
        cases = {
            "everyday": "everyday",                       # 非日期 → [格式]
            "placeholder": "—",                           # 占位符 → 提示
            "space_note": "2026-08-08 凌晨",              # 空格注释 → 规范化提示（兼陈旧）
            "ok_note": "2026-11-08（凌晨长注释）",        # 全角注释 → 完全合法
            "future_day": "2027-01-01",                   # 未来 → [格式]
            "impossible_day": "2026-13-45",               # 非法日期 → [格式]
        }
        rows, tag_lines = [], []
        for i, (stem, val) in enumerate(cases.items()):
            text = contact_yaml(stem, platform_block=f'  qq: "2000{i}"', last_contact=val)
            self.write(f"contacts/{stem}.md", text)
            rows.append(f"| {stem} | | 身份 | [[S1]] | 密友 | {val} | [[{stem}]] |")
            tag_lines.append(f"- [[{stem}]] — 测试")
        self.write("tags/school/S1.md", tag_md("S1", tag_lines))
        self.write("INDEX.md", index_md(rows, [], tags_rows=["S1"]))
        r = self.result(stale_days=90)
        fmt_errors = self.msgs(r["issues"], "格式", ag.ERR)
        self.assertEqual(len(fmt_errors), 3)
        self.assertTrue(any("everyday" in m for m in fmt_errors))
        hints = self.msgs(r["issues"], "提示", ag.HINT)
        self.assertTrue(any("占位符「—」" in m for m in hints))
        self.assertTrue(any("规范化" in m for m in hints))
        self.assertTrue(any("space_note" in m and "未联系" in m for m in hints))   # 兼陈旧提示
        self.assertFalse(any("ok_note" in m and "last_contact" in m for m in hints))

    def test_staleness_threshold_boundary(self):
        text = contact_yaml("甲", last_contact=str(TODAY - datetime.timedelta(days=91)))
        self.write("contacts/甲.md", text)
        self.write("tags/school/S1.md", tag_md("S1", ["- [[甲]] — 测试"]))
        self.write("INDEX.md", index_md(
            ["| 甲 | jia | 身份 | [[S1]] | 密友 | 2026-08-24 | [[甲]] |"],
            [], tags_rows=["S1"]))
        r = self.result(stale_days=90)
        self.assertEqual(len(r["last_contact"]["stale"]), 1)
        self.assertEqual(len(r["last_contact"]["invalid"]), 0)
        r2 = self.result(stale_days=120)
        self.assertEqual(len(r2["last_contact"]["stale"]), 0)


class TestGraphRules(VaultCase):
    def test_orphan_requires_tag_link(self):
        """只链其他联系人不算入圈：零标签链接 = 孤儿（新口径）。"""
        a = contact_yaml("甲").replace("## 触发标签\n\n[[S1]]", "## 触发标签\n\n- 暂无")
        # 再链向乙
        a = a.replace("## 备注", "## 链向\n\n[[乙]]\n\n## 备注")
        self.write("contacts/甲.md", a)
        self.write("contacts/乙.md", contact_yaml("乙"))
        self.write("tags/school/S1.md", tag_md("S1", ["- [[乙]] — 测试"]))
        self.write("INDEX.md", index_md(
            ["| 甲 | jia | 身份 | | 密友 | 2026-11-20 | [[甲]] |",
             "| 乙 | yi | 身份 | [[S1]] | 密友 | 2026-11-20 | [[乙]] |"],
            [], tags_rows=["S1"]))
        r = self.result()
        self.assertEqual(len(self.msgs(r["issues"], "孤立", ag.ERR)), 1)
        self.assertIn("甲", self.msgs(r["issues"], "孤立", ag.ERR)[0])

    def test_html_comment_placeholders_ignored(self):
        text = contact_yaml("甲").replace(
            "## 备注\n\n- 无",
            "## 备注\n\n<!-- 示例：[[不存在的占位]]、[[联系人姓名]] -->\n\n- 无")
        self.write("contacts/甲.md", text)
        self.write("tags/school/S1.md", tag_md("S1", ["- [[甲]] — 测试"]))
        self.write("INDEX.md", index_md(
            ["| 甲 | jia | 身份 | [[S1]] | 密友 | 2026-11-20 | [[甲]] |"],
            [], tags_rows=["S1"]))
        r = self.result()
        self.assertEqual(r["issues"].count(severity=ag.ERR), 0,
                         msg="\n".join(r["issues"].errors()))

    def test_split_table_row_masks_alias_pipe(self):
        cells = ag.split_table_row("| 昵称 | [[目标页|别名]] | 尾 |")
        self.assertEqual(cells, ["昵称", "[[目标页|别名]]", "尾"])


class TestDegradedMode(VaultCase):
    """无 pyyaml 环境：结构检查全保留，YAML 相关检查整体声明跳过、零误导。"""

    def test_degraded_skips_yaml_checks_without_false_hints(self):
        self.baseline()
        orig_yaml, orig_flag = ag.yaml, ag.HAS_YAML
        ag.yaml, ag.HAS_YAML = None, False
        try:
            r = self.result()
            self.assertTrue(any("降级模式" in m for m in r["issues"].hints()))
            self.assertEqual(r["issues"].count(severity=ag.ERR), 0,
                             msg="\n".join(r["issues"].errors()))
            # 不得因 body 不可见而误报空值/杂键
            self.assertEqual(r["last_contact"]["empty"], [])
            self.assertEqual(r["schema"]["unknown_keys"], [])
            self.assertEqual(r["collisions"], [])
            # 结构检查照常
            self.assertEqual(r["index"]["rows"], 2)
            self.assertEqual(r["membership"]["missing"], [])
            self.assertEqual(r["index"]["missing_contacts"], [])
        finally:
            ag.yaml, ag.HAS_YAML = orig_yaml, orig_flag

    def test_strict_refuses_degraded_mode(self):
        self.baseline()
        orig_yaml, orig_flag = ag.yaml, ag.HAS_YAML
        ag.yaml, ag.HAS_YAML = None, False
        try:
            rc = ag.main([self.dir, "--strict"])
            self.assertEqual(rc, 2)
            rc = ag.main([self.dir])  # 非门禁模式仍可降级运行
            self.assertEqual(rc, 0)
        finally:
            ag.yaml, ag.HAS_YAML = orig_yaml, orig_flag


class TestCLI(VaultCase):
    def test_strict_exit_codes_and_json_purity(self):
        self.baseline()
        rc = ag.main([self.dir, "--strict"])
        self.assertEqual(rc, 0)
        self.write("INDEX.md", index_md(
            ["| 甲 | jia | 身份 | [[S1]] | 密友 | 2026-11-20 | [[甲]] || 坏行 |"],
            [("R1", "1 已登记 / 1 仅名单")], tags_rows=["S1", "S2"]))
        rc = ag.main([self.dir, "--strict"])
        self.assertEqual(rc, 1)
        # 提示级不阻断：制造纯提示场景（非规范键 → 杂键提示）
        self.write("contacts/甲.md", contact_yaml("甲").replace("platform:", "platforms:"))
        self.baseline()  # 重写恢复
        self.write("contacts/甲.md", contact_yaml("甲").replace("platform:", "platforms:"))
        rc = ag.main([self.dir, "--strict"])
        self.assertEqual(rc, 0)

    def test_json_schema_v2_shape(self):
        self.baseline()
        r = self.result()
        doc = ag.to_json(r)
        self.assertEqual(doc["schema_version"], 2)
        for key in ("errors", "hints", "issues_detail", "index", "membership",
                    "schema", "collisions", "last_contact", "graph", "redundant_edges"):
            self.assertIn(key, doc)
        for key in ("errors", "hints", "membership_missing", "pseudo_tag_rows",
                    "id_collisions", "last_contact_stale"):
            self.assertIn(key, doc["stats"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

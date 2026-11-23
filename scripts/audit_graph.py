"""
人际关系图谱审计脚本
=====================

用于 Obsidian vault 中联系人知识图谱的完整性校验和结构分析。

检查能力：
  1. [[wiki-links]] 断链、孤立节点（联系人须至少挂一个标签）
  2. 名单（rosters/）：成员节解析（节名在首个括号前含「成员」），
     状态列（已登记/仅名单/本人）在任意列数下右起定位，
     链接与状态一致、升级提示、本人行规范
  3. 标签页成员双向核对：标签页「联系人」列表 ↔ 联系人身上标签（漂移即报）
  4. INDEX.md 自动对账：总览行完整性、坏行（合并行/列数不符）、名单计数、
     标签导航、INDEX 双链可解析、旧式纯文本伪标签、检索列（缩写·网名）
  5. schema 校验：YAML 解析失败（不再静默）、未知键迁移提示、
     昵称子键提示、frontmatter 约定
  6. 平台 ID 跨文件碰撞（同一 QQ/学号/邮箱出现在两人档案）
  7. last_contact 格式与陈旧度（只报告，绝不改动数据）
  8. 冗余标签边候选（仅共享联系人间接相连）

用法：
  python audit_graph.py <vault_path> [--report] [--json] [--strict] [--stale-days N]

输出：
  默认       紧凑摘要（统计 + 各类计数 + 全部错误 + 提示计数）
  --report   完整人类可读报告（分析节全开）
  --json     机器可读 JSON（schema_version 2；进度信息走 stderr，stdout 纯 JSON）
  --strict   存在错误级问题时退出码 1（提示级永不失败；陈旧/迁移类提示不阻断）
退出码：0 正常；1 有错误且 --strict；2 用法/路径错误/--strict 遇降级模式

严重度模型：
  错误级 [断链] [孤立] [名单] [索引] [标签页] [schema] [冲突] [格式] —— 事实性损坏或规范违背
  提示级 [提示] —— 迁移建议、陈旧度、可升级成员等，需人工分诊

降级模式：pyyaml 缺失时脚本仍可运行——断链/孤立/名单/INDEX/标签页等结构检查
不依赖 YAML，照常全部执行；依赖 YAML 的检查（schema/杂键、ID 碰撞、last_contact、
检索列昵称）整体跳过并输出一条醒目提示，绝不产生误导性结果；frontmatter 与
备注节检查用纯文本解析保留。--strict 在降级模式拒绝运行（门禁不能半盲）。
安装 pyyaml：python -m venv .venv && .venv/Scripts/pip install pyyaml（Unix 用 .venv/bin/pip）
"""

import os
import re
import sys
import json
import argparse
import datetime
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

try:
    import yaml
    HAS_YAML = True
except ImportError:  # pyyaml 缺失 → 自动降级为结构审计（见 run_audit）
    yaml = None
    HAS_YAML = False

# Windows 下重定向/管道到文件时 stdout 默认用 cp936，emoji 会直接抛
# UnicodeEncodeError——统一切到 UTF-8，非法字符降级替换
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ─── 常量 ──────────────────────────────────────────────────────────────────

# 模板/示例注释里常见的占位双链，不算断链
PLACEHOLDER_LINKS = {"双链", "tag-name", "双链示例", "联系人姓名", "标签名", "wiki-links"}

# 规范键名（正文 yaml 围栏顶层）
CANONICAL_KEYS = {"nickname", "real_name", "platform", "identity",
                  "met", "strength", "last_contact"}

# 未知顶层键 → 迁移建议
UNKNOWN_KEY_SUGGESTION = {
    "qq_nickname": "platform.qq_nickname（昵称子键）",
    "wechat_nickname": "platform.wechat_nickname（昵称子键）",
    "student_id": "platform.bupt 之类学号子键（若与现有值相同则直接删除）",
    "alias": "正文「备注」小节或 platform.other",
    "high_school": "identity 一句话或正文备注",
}

# 参与碰撞检测的"账号 ID"子键（排除 other / nicknames / *_nickname）
ID_SUBKEYS = {"qq", "wechat", "bupt", "email", "phone",
              "bilibili", "luogu", "codeforces", "github"}

# 名单状态列合法值（本人 = 名单拥有者自己的行，不建档、不链接、不入计数）
ROSTER_STATUSES = ("已登记", "仅名单", "本人")

# 规范 7 键之外的强度词表已废除：strength 是自由词，本脚本不校验、不提示。

ERR, HINT = "error", "hint"


def eprint(*args, **kwargs):
    """进度信息走 stderr，保证 --json 的 stdout 纯净。"""
    print(*args, file=sys.stderr, **kwargs)


# ─── 第 1 部分：解析器 ─────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """剥掉 HTML 注释（含跨行），避免模板占位/说明里的 [[双链]] 被当成真实链接。"""
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def parse_wiki_links(text: str) -> List[str]:
    """
    从文本中提取所有 [[双链]] 目标。

    支持格式：
      [[目标页面]]
      [[目标页面|显示文本]]
      [[目标页面#锚点]]
      [[目标页面#锚点|显示文本]]

    返回纯目标名列表（去重、去显示文本、去锚点）。
    """
    pattern = r'\[\[([^\]|#]+)(?:[|#][^\]]+)?\]\]'
    matches = re.findall(pattern, text)
    seen = set()
    result = []
    for m in matches:
        target = m.strip()
        if target and target not in seen:
            seen.add(target)
            result.append(target)
    return result


def parse_frontmatter(text: str) -> Tuple[dict, List[str]]:
    """
    从 Markdown 文本中提取 YAML frontmatter。

    返回 (dict, 错误列表)；无 frontmatter 返回 ({}, [])，解析失败返回错误。
    无 pyyaml 时降级为简单 `key: value` 正则解析（够用于 title/type 判定）。
    """
    match = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
    if not match:
        return {}, []
    if yaml is None:
        fm = {}
        for line in match.group(1).splitlines():
            m = re.match(r"^([A-Za-z_][\w-]*)[ \t]*:[ \t]*(.*)$", line.strip())
            if m:
                fm[m.group(1)] = m.group(2).strip().strip('"').strip("'")
        return fm, []
    try:
        return yaml.safe_load(match.group(1)) or {}, []
    except yaml.YAMLError as e:
        return {}, [f"frontmatter YAML 解析失败：{str(e).splitlines()[0] if str(e) else e}"]


def parse_yaml_blocks(text: str) -> Tuple[dict, List[str]]:
    """
    提取 Markdown 正文中 ```yaml 围栏块里的 YAML，合并为一个 dict。

    联系人模板把结构化字段放在正文围栏块里（而非 frontmatter），
    见 assets/contact-template.md。
    返回 (合并 dict, 错误列表)——解析失败不再静默吞掉：
    典型坏例是双引号标量里嵌 ASCII 引号，整块字段会全部失踪。
    """
    merged = {}
    errors = []
    yml = yaml
    if yml is None:
        return {}, []  # 降级：不解析正文 YAML，由 run_audit 统一声明跳过的检查
    for i, block in enumerate(re.findall(r"^```yaml\s*\n(.*?)\n```", text, re.DOTALL | re.MULTILINE), 1):
        try:
            data = yml.safe_load(block)
            if isinstance(data, dict):
                merged.update(data)
        except yml.YAMLError as e:
            first = str(e).strip().splitlines()
            mark = ""
            m = re.search(r"line (\d+)", str(e))
            if m:
                mark = f"（块内第 {m.group(1)} 行）"
            reason = first[-1] if first else str(e)
            errors.append(f"正文 yaml 围栏块 #{i}{mark} 解析失败：{reason}"
                          f"——该块字段未入库，常见原因是双引号标量内嵌 ASCII \"")
    return merged, errors


_WIKI_SPAN = re.compile(r"\[\[[^\]]*\]\]")


def split_table_row(line: str) -> List[str]:
    """
    切分 Markdown 表格行为单元格列表。

    先掩码 [[…]] 内部的 `|`（护住 [[目标|别名]]），切分后还原。
    """
    masked = _WIKI_SPAN.sub(lambda m: m.group(0).replace("|", "\x00"), line)
    stripped = masked.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [c.strip().replace("\x00", "|") for c in stripped.split("|")]


def is_separator_row(cells: List[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-+:?", c) for c in cells)


def parse_md_table(lines: List[str], start: int, end: int) -> Tuple[Optional[List[str]], List[Tuple[int, List[str]]]]:
    """
    在 lines[start:end] 范围内解析第一个 Markdown 表格。

    返回 (表头 cells 或 None, [(绝对行号(1 起), cells), …数据行])。
    逐行剥 HTML 注释；跳过表头与分隔行；注释剥空的行为忽略。
    """
    header = None
    rows = []
    for idx in range(start, end):
        raw = lines[idx].strip()
        if not raw.startswith("|"):
            continue
        line = clean_text(raw)
        if not line.startswith("|"):
            continue
        cells = split_table_row(line)
        if header is None:
            header = cells
            continue
        if is_separator_row(cells):
            continue
        if not any(cells):
            continue
        rows.append((idx + 1, cells))
    return header, rows


def parse_roster_members(text: str) -> Tuple[List[dict], bool]:
    """
    从名单文件的成员小节解析成员表格（见 assets/roster-template.md）。

    成员节标题 = 首个括号之前含「成员」二字的节名（`## 成员`、`## 项目成员（5 人 · …）`、
    `## 主要成员` 均可）；「成员」只出现在括号内或别处的不算——
    `## 分工线（…主要成员介绍…）`、`## 指导教师`、`## 队籍判定规则` 一律不误中。

    每个成员：{name, role, status, linked, self_role_marker}
      - name   = 联系人姓名（已登记取 [[双链]] 目标，其余取姓名列原文）
      - role   = 角色列原文
      - status = 状态值（已登记 / 仅名单 / 本人），在任意列数下从右往左找
                 第一个恰好等于合法值的单元格（兼容 性别/QQ/学号/手机 等额外列）
      - linked = 姓名列是否含 [[双链]]
      - self_role_marker = 角色列文本是否含「本人」（用于提示统一自编码）

    返回 (成员列表, 是否找到成员节)。
    """
    section = re.search(
        r"^##[ \t]*(?=[^（(\n]*成员)[^\n]*\n(.*?)(?=\n##[ \t]|\Z)",
        text, re.DOTALL | re.MULTILINE)
    if not section:
        return [], False

    members = []
    for line in section.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        line = re.sub(r"<!--.*?-->", "", line, flags=re.DOTALL)
        if not line.startswith("|"):
            continue
        cells = split_table_row(line)
        if len(cells) < 3:
            continue
        name_cell, role = cells[0], cells[1]
        # 状态列兼容 3 列以上的表格（如含「性别」列）：从右往左找第一个合法状态值
        status = next(
            (c for c in reversed(cells[2:]) if c in ROSTER_STATUSES),
            cells[2],
        )
        # 跳过表头行与分隔行
        if name_cell == "姓名" or is_separator_row(cells):
            continue
        # 注释剥掉后占位行可能只剩空姓名
        if not name_cell:
            continue
        link_match = re.search(r"\[\[([^\]|#]+)", name_cell)
        members.append({
            # 已登记成员统一用档案名，输出更自然
            "name": link_match.group(1).strip() if link_match else name_cell,
            "role": role,
            "status": status,
            "linked": bool(link_match),
            "self_role_marker": "本人" in role,
        })
    return members, True


_TAG_MEMBER_HEADING = (
    r"^##[ \t]*(?:[0-9一二三四五六七八九十]+[、.．][ \t]*)?"
    r"(?:相关联系人|联系人|Related\ Contacts)(?:[（(][^\n]*[)）])?[ \t]*\n"
)


def parse_tag_members(text: str, contact_names: set) -> Tuple[bool, List[str], List[str]]:
    """
    从标签文件解析「联系人」节的成员列表。

    只读标题匹配 (编号前缀)?(相关联系人|联系人|Related Contacts) 的小节；
    其余小节（找谁问什么/意向投票/组织信息等表格）一律不算成员列表——
    hub 型标签页可以没有联系人节。

    返回 (是否有成员节, wiki 成员目标列表, 纯文本成员列表)：
      - 项目符号行/表格行里的第一个 [[双链]] → wiki 成员
      - 无链接的行，若「名字部分」（截断到 ——/–/（/| 之前）恰为联系人档案名
        → 纯文本成员（提示 wikify）
    """
    m = re.search(_TAG_MEMBER_HEADING, text, re.MULTILINE)
    if not m:
        return False, [], []
    body = text[m.end():]
    stop = re.search(r"\n##[ \t]", body)
    if stop:
        body = body[:stop.start()]
    body = clean_text(body)

    linked, plain = [], []
    for line in body.splitlines():
        line = line.strip()
        is_item = line.startswith(("- ", "* ", "|"))
        if not is_item:
            continue
        if line.startswith(("|",)):
            cells = split_table_row(line)
            if not cells or cells[0] == "姓名" or is_separator_row(cells):
                continue
            content = cells[0]
        else:
            content = line[2:]
        targets = parse_wiki_links(content)
        if targets:
            linked.append(targets[0])
            continue
        # 纯文本：截断注释部分后比对档案名
        name = re.split(r"\s+[—–]\s+", content, maxsplit=1)[0]
        name = re.split(r"[（(]", name, maxsplit=1)[0].strip()
        name = name.replace("**", "").strip()
        if name and name in contact_names:
            plain.append(name)
    return True, linked, plain


def _norm_int_two(cell: str) -> Optional[Tuple[int, int]]:
    """从名单计数格提取 (已登记, 仅名单)；兼容旧 'N + M'；失败返回 None。"""
    reg = re.search(r"(\d+)\s*已登记", cell)
    only = re.search(r"(\d+)\s*仅名单", cell)
    if reg:
        return int(reg.group(1)), int(only.group(1)) if only else 0
    legacy = re.search(r"(\d+)\s*\+\s*(\d+)", cell)
    if legacy:
        return int(legacy.group(1)), int(legacy.group(2))
    return None


def parse_index(text: str) -> dict:
    """
    解析 INDEX.md 的三个区：联系人总览 / 名单 / 按标签检索（三层）。

    列一律按表头名定位（兼容 6/7 列，检索列表头可为「缩写」或「缩写·网名」）。
    行主键 = 链接列的第一个 [[双链]] 目标（昵称列常带注释，不可靠）。
    坏行（cell 数 ≠ 表头数）单列出来，不参与行↔文件对账。
    """
    lines = clean_text(text).splitlines()
    result = {
        "overview_header": None, "overview_rows": [], "overview_malformed": [],
        "roster_rows": [], "tag_nav": {"school": [], "field": [], "city": []},
        "all_links": parse_wiki_links(clean_text(text)),
    }

    # ── 联系人总览 ──
    bounds = _section_to_next_h2(lines, "联系人总览")
    if bounds:
        header, rows = parse_md_table(lines, *bounds)
        result["overview_header"] = header
        if header:
            def col(*names):
                for i, c in enumerate(header or []):
                    if any(n in c for n in names):
                        return i
                return None
            i_link, i_tag = col("链接"), col("触发标签")
            i_search = col("缩写·网名", "缩写", "网名")
            for ln_no, cells in rows:
                if len(cells) != len(header):
                    result["overview_malformed"].append({"line": ln_no, "cells": len(cells)})
                    continue
                links = parse_wiki_links(cells[i_link]) if i_link is not None and i_link < len(cells) else []
                tag_cell = cells[i_tag] if i_tag is not None and i_tag < len(cells) else ""
                search_cell = cells[i_search] if i_search is not None and i_search < len(cells) else ""
                result["overview_rows"].append({
                    "line": ln_no,
                    "key": links[0] if links else None,
                    "line_links": links,
                    "tag_cell": tag_cell,
                    "tag_links": parse_wiki_links(tag_cell),
                    "search_cell": search_cell,
                    "search_idx": i_search,
                })

    # ── 名单导航 ──
    bounds = _section_to_next_h2(lines, "名单")
    if bounds:
        header, rows = parse_md_table(lines, *bounds)
        if header:
            def rcol(*names):
                for i, c in enumerate(header or []):
                    if any(n in c for n in names):
                        return i
                return None
            i_link = rcol("链接")
            i_count = rcol("已登记", "仅名单")
            if i_count is None:
                i_count = len(header) - 2
            for ln_no, cells in rows:
                if len(cells) != len(header):
                    continue
                links = parse_wiki_links(cells[i_link]) if i_link is not None and i_link < len(cells) else []
                count_cell = cells[i_count] if i_count < len(cells) else ""
                counts = _norm_int_two(count_cell)
                result["roster_rows"].append({
                    "line": ln_no,
                    "key": links[0] if links else cells[0],
                    "counts": counts,
                    "count_cell": count_cell,
                    "mentions_self": "本人" in count_cell,
                })

    # ── 按标签检索 ──
    bounds = _section_to_next_h2(lines, "按标签检索")
    if bounds:
        layer_heading = {"学校": "school", "专业方向": "field", "城市": "city"}

        def flush_segment(layer, s, e):
            if layer is None:
                return
            header, rows = parse_md_table(lines, s, e)
            if not header:
                return
            i_link = len(header) - 1
            for i, c in enumerate(header):
                if "标签文件" in c or "链接" in c:
                    i_link = i
                    break
            for ln_no, cells in rows:
                if len(cells) != len(header):
                    continue
                links = parse_wiki_links(cells[i_link]) if i_link < len(cells) else []
                result["tag_nav"][layer].append({
                    "line": ln_no,
                    "key": links[0] if links else cells[0],
                })

        cur_layer = None
        seg_start = bounds[0]
        h3 = re.compile(r"^###[ \t]*(.+?)[ \t]*$")
        for idx in range(bounds[0], bounds[1]):
            mm = h3.match(lines[idx])
            if mm and mm.group(1).strip() in layer_heading:
                flush_segment(cur_layer, seg_start, idx)
                cur_layer = layer_heading[mm.group(1).strip()]
                seg_start = idx + 1
        flush_segment(cur_layer, seg_start, bounds[1])
    return result


def _section_to_next_h2(lines: List[str], title: str) -> Optional[Tuple[int, int]]:
    """`^## <title>` 到下一个 `^## `（不含 ###）的行区间。"""
    start = None
    for i, ln in enumerate(lines):
        if re.match(rf"^##[ \t]*{re.escape(title)}[ \t]*$", ln) or \
           re.match(rf"^##[ \t]*{re.escape(title)}[ \t]*(?:[（(].*)?$", ln):
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start, len(lines)):
        if re.match(r"^##[ \t]", lines[i]):
            end = i
            break
    return start, end


# ─── 第 2 部分：文件扫描器 ─────────────────────────────────────────────────

def scan_vault(vault_path: str) -> Tuple[dict, dict, dict, Optional[str]]:
    """
    扫描整个 vault，返回 (联系人数据, 标签数据, 名单数据, INDEX.md 文本或 None)。

    联系人：{名字: {frontmatter, yaml_body, yaml_errors, wiki_links, body_headings, text, file_path}}
    标签：  {名字: {frontmatter, wiki_links, type, text, file_path}}
    名单：  {名字: {members, has_member_section, wiki_links, text, file_path}}
    """
    vault = Path(vault_path)
    contacts, tags, rosters = {}, {}, {}

    contacts_dir = vault / "contacts"
    if contacts_dir.exists():
        for md_file in sorted(contacts_dir.glob("*.md")):
            text = md_file.read_text(encoding="utf-8-sig", errors="replace")
            fm, fm_errors = parse_frontmatter(text)
            body, body_errors = parse_yaml_blocks(text)
            name = md_file.stem
            contacts[name] = {
                "frontmatter": fm,
                "yaml_body": body,
                "yaml_errors": fm_errors + body_errors,
                "wiki_links": parse_wiki_links(clean_text(text)),
                "body_headings": re.findall(r"^##[ \t]*(.+?)[ \t]*$", text, re.MULTILINE),
                "text": text,
                "file_path": str(md_file),
            }

    tags_dir = vault / "tags"
    if tags_dir.exists():
        for md_file in sorted(tags_dir.rglob("*.md")):
            text = md_file.read_text(encoding="utf-8-sig", errors="replace")
            fm, _ = parse_frontmatter(text)
            rel = md_file.relative_to(tags_dir)
            tag_type = rel.parts[0] if len(rel.parts) > 1 else "root"
            name = md_file.stem
            tags[name] = {
                "frontmatter": fm,
                "yaml_body": parse_yaml_blocks(text)[0],
                "wiki_links": parse_wiki_links(clean_text(text)),
                "type": tag_type,
                "text": text,
                "file_path": str(md_file),
            }

    rosters_dir = vault / "rosters"
    if rosters_dir.exists():
        for md_file in sorted(rosters_dir.glob("*.md")):
            text = md_file.read_text(encoding="utf-8-sig", errors="replace")
            members, found = parse_roster_members(text)
            name = md_file.stem
            rosters[name] = {
                "members": members,
                "has_member_section": found,
                "wiki_links": parse_wiki_links(clean_text(text)),
                "text": text,
                "file_path": str(md_file),
            }

    index_file = vault / "INDEX.md"
    index_text = None
    if index_file.exists():
        index_text = index_file.read_text(encoding="utf-8-sig", errors="replace")

    return contacts, tags, rosters, index_text


# ─── 第 3 部分：图结构构建 ──────────────────────────────────────────────────

def build_graph(contacts: dict, tags: dict) -> dict:
    """
    构建知识图谱结构（联系人 ↔ 标签）。

    contact_to_tags 是成员核对与孤儿判定的唯一事实源：
    YAML trigger_tags 字段（若存在）+ 正文里解析到标签文件的 [[双链]]。
    """
    contact_to_tags: Dict[str, Set[str]] = {}
    for name, data in contacts.items():
        raw_tags = (
            data["frontmatter"].get("trigger_tags")
            or data.get("yaml_body", {}).get("trigger_tags")
            or []
        )
        tag_set = set()
        for t in raw_tags:
            tag_set.add(str(t).strip("[] ").strip())
        for link in data["wiki_links"]:
            if link in tags:
                tag_set.add(link)
        contact_to_tags[name] = tag_set

    tag_to_contacts: Dict[str, Set[str]] = defaultdict(set)
    for contact_name, tag_set in contact_to_tags.items():
        for tag in tag_set:
            if tag in tags:
                tag_to_contacts[tag].add(contact_name)

    tag_to_tags: Dict[str, Set[str]] = {}
    for tag_name, tag_data in tags.items():
        linked = set()
        for link in tag_data["wiki_links"]:
            if link in tags and link != tag_name:
                linked.add(link)
        tag_to_tags[tag_name] = linked

    structural_edges = set()
    contact_bridged_edges: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    all_tags = list(tags.keys())
    for i in range(len(all_tags)):
        for j in range(i + 1, len(all_tags)):
            a, b = all_tags[i], all_tags[j]
            if a in tag_to_tags.get(b, set()) or b in tag_to_tags.get(a, set()):
                structural_edges.add((a, b))
            shared = tag_to_contacts.get(a, set()) & tag_to_contacts.get(b, set())
            if shared:
                contact_bridged_edges[(a, b)] = shared

    return {
        "contact_to_tags": {k: sorted(v) for k, v in contact_to_tags.items()},
        "tag_to_contacts": {k: sorted(v) for k, v in tag_to_contacts.items()},
        "tag_to_tags": {k: sorted(v) for k, v in tag_to_tags.items()},
        "structural_edges": sorted(structural_edges),
        "contact_bridged_edges": {
            str(k): sorted(v) for k, v in contact_bridged_edges.items()
        },
    }


# ─── 问题收集器 ─────────────────────────────────────────────────────────────

class Issues:
    """统一的问题收集器：错误级 + 提示级。"""

    def __init__(self):
        self.detail: List[dict] = []

    def add(self, category: str, severity: str, message: str,
            file: Optional[str] = None, line: Optional[int] = None):
        self.detail.append({
            "category": category, "severity": severity,
            "message": message, "file": file, "line": line,
        })

    def errors(self) -> List[str]:
        return [f"[{i['category']}] {i['message']}"
                for i in self.detail if i["severity"] == ERR]

    def hints(self) -> List[str]:
        return [f"[{i['category']}] {i['message']}"
                for i in self.detail if i["severity"] == HINT]

    def count(self, category: Optional[str] = None, severity: Optional[str] = None) -> int:
        return sum(1 for i in self.detail
                   if (category is None or i["category"] == category)
                   and (severity is None or i["severity"] == severity))

    def structured(self, category: str, severity: str) -> List[dict]:
        return [i for i in self.detail
                if i["category"] == category and i["severity"] == severity]


# ─── 第 4 部分：完整性校验 ──────────────────────────────────────────────────

def audit_integrity(contacts: dict, tags: dict, graph: dict,
                    rosters: dict, issues: Issues):
    """
    断链 / 孤立 / 名单结构与状态检查。

    1. 联系人、标签文件里的 [[链接]] 必须能解析到 联系人/标签/名单（白名单除外）
    2. 孤立联系人 = 没有挂任何**标签**（只链向其他联系人不算入圈）
    3. 孤立标签 = 没有任何联系人引用
    4. 名单：[[双链]] 只允许指向联系人；状态列合法值 已登记/仅名单/本人；
       已登记必须带链接、仅名单/本人不得带链接；本人行每名单至多一行；
       仅名单成员已有档案 → 升级提示；角色含「本人」但状态不是本人 → 统一编码提示
    """
    rosters = rosters or {}
    all_valid_targets = set(contacts.keys()) | set(tags.keys()) | set(rosters.keys())

    for kind, holder in (("联系人", contacts), ("标签", tags)):
        for name, data in holder.items():
            for link in data["wiki_links"]:
                if link not in all_valid_targets and link not in PLACEHOLDER_LINKS:
                    issues.add("断链", ERR, f"{kind} '{name}' 中的 [[{link}]] 找不到对应文件",
                               file=data.get("file_path"))

    for name in contacts:
        if not graph["contact_to_tags"].get(name):
            issues.add("孤立", ERR, f"联系人 '{name}' 没有挂任何标签（触发标签小节为空）",
                       file=contacts[name].get("file_path"))

    for tag_name in tags:
        if not graph["tag_to_contacts"].get(tag_name):
            issues.add("孤立", ERR, f"标签 '{tag_name}' 没有被任何联系人引用",
                       file=tags[tag_name].get("file_path"))

    for roster_name, roster_data in rosters.items():
        if not roster_data["has_member_section"]:
            issues.add("提示", HINT,
                       f"名单 '{roster_name}' 未找到可解析的成员节"
                       f"（标题应为「## 成员」或「## 项目成员（…）」）",
                       file=roster_data.get("file_path"))
        for link in roster_data["wiki_links"]:
            if link not in contacts and link not in PLACEHOLDER_LINKS:
                issues.add("名单", ERR,
                           f"'{roster_name}' 中的 [[{link}]] 不是已登记联系人"
                           f"（名单只允许链接 contacts/ 下的档案）",
                           file=roster_data.get("file_path"))

        self_count = 0
        for m in roster_data["members"]:
            if m["status"] not in ROSTER_STATUSES:
                issues.add("名单", ERR,
                           f"'{roster_name}' 成员 '{m['name']}' 状态列值无效："
                           f"「{m['status']}」（只允许 已登记 / 仅名单 / 本人）",
                           file=roster_data.get("file_path"))
                continue
            if m["status"] == "已登记" and not m["linked"]:
                issues.add("名单", ERR,
                           f"'{roster_name}' 成员 '{m['name']}' 状态为「已登记」"
                           f"但姓名未用 [[双链]] 链接档案",
                           file=roster_data.get("file_path"))
            elif m["status"] == "仅名单" and m["linked"]:
                issues.add("名单", ERR,
                           f"'{roster_name}' 成员 '{m['name']}' 状态为「仅名单」"
                           f"但姓名带了 [[双链]]（仅名单成员不应链接档案）",
                           file=roster_data.get("file_path"))
            elif m["status"] == "本人":
                self_count += 1
                if m["linked"]:
                    issues.add("名单", ERR,
                               f"'{roster_name}' 的「本人」行不应带 [[双链]]"
                               f"（名单拥有者不建档案）",
                               file=roster_data.get("file_path"))
            if m["status"] == "仅名单" and not m["linked"] and m["name"] in contacts:
                issues.add("提示", HINT,
                           f"'{roster_name}' 仅名单成员 '{m['name']}' 已有人脉档案，"
                           f"可升级为 [[{m['name']}]]",
                           file=roster_data.get("file_path"))
            if m["self_role_marker"] and m["status"] != "本人":
                issues.add("提示", HINT,
                           f"'{roster_name}' 成员 '{m['name']}' 角色列标注了「本人」"
                           f"但状态是「{m['status']}」——规范自编码为 状态=本人"
                           f"（纯文本名、无双链、不建档、不入计数）",
                           file=roster_data.get("file_path"))
        if self_count > 1:
            issues.add("名单", ERR,
                       f"'{roster_name}' 有 {self_count} 行状态为「本人」"
                       f"（每份名单至多一行）",
                       file=roster_data.get("file_path"))


# ─── 第 5 部分：标签页成员双向核对 ─────────────────────────────────────────

def audit_membership(contacts: dict, tags: dict, graph: dict, issues: Issues) -> dict:
    """
    标签页「联系人」节 ↔ 联系人身上标签的双向核对。

    事实源：graph.contact_to_tags（YAML trigger_tags + 正文双链）。
      - 联系人带标签 T，但 T 页成员列表没列 → [标签页] 错误（正向漂移，召回缺口）
      - T 页列了 X：X 不是联系人 / X 是联系人但没挂 T → [标签页] 错误（反向漂移）
    修复方向（补页 vs 改标签）留给人按 2c 逐例决定，审计只报不选。

    没有成员节的标签页（hub 型：找谁问什么/投票表等）跳过并记录，不算问题。
    """
    contact_names = set(contacts.keys())
    missing_pairs, reverse_pairs, plain_pairs, skipped = [], [], [], []

    for tag_name, tag_data in tags.items():
        found, linked, plain = parse_tag_members(tag_data["text"], contact_names)
        if not found:
            skipped.append(tag_name)
            continue
        listed = set(linked)
        for name in plain:
            listed.add(name)
            plain_pairs.append({"tag": tag_name, "contact": name})

        expected = set(graph["tag_to_contacts"].get(tag_name, []))

        for contact in sorted(expected - listed):
            missing_pairs.append({"tag": tag_name, "contact": contact})
            issues.add("标签页", ERR,
                       f"联系人 '{contact}' 挂了标签 [[{tag_name}]]，"
                       f"但标签页 '{tag_name}' 的联系人列表没列他（触发式召回缺口）",
                       file=tag_data.get("file_path"))
        for entry in sorted(linked):
            if entry not in contact_names:
                reverse_pairs.append({"tag": tag_name, "name": entry, "reason": "非联系人"})
                issues.add("标签页", ERR,
                           f"标签页 '{tag_name}' 的联系人列表里的 [[{entry}]] "
                           f"不是 contacts/ 下的档案",
                           file=tag_data.get("file_path"))
            elif entry not in expected:
                reverse_pairs.append({"tag": tag_name, "name": entry, "reason": "未挂此标签"})
                issues.add("标签页", ERR,
                           f"标签页 '{tag_name}' 列了联系人 '{entry}'，"
                           f"但该联系人没有挂 [[{tag_name}]]（方向二选一：补标签或移出列表）",
                           file=tag_data.get("file_path"))

    for p in plain_pairs:
        issues.add("提示", HINT,
                   f"标签页 '{p['tag']}' 以纯文本列了联系人 '{p['contact']}'，"
                   f"建议改为 [[{p['contact']}]]",
                   file=tags[p["tag"]].get("file_path"))

    return {"missing": missing_pairs, "reverse": reverse_pairs,
            "plain_text": plain_pairs, "skipped_tags": skipped}


# ─── 第 6 部分：INDEX 对账 ──────────────────────────────────────────────────

def _contact_nickname_values(data: dict) -> List[str]:
    """收集联系人已知的网络昵称值（platform.*_nickname / 顶层 *_nickname）。

    `nicknames`/`other` 这类自由文案字段不算——里面常混注释，
    由专门的迁移提示处理，不用于检索列核对。"""
    values = []
    body = data.get("yaml_body") or {}
    platform = body.get("platform") or {}
    pairs = []
    if isinstance(platform, dict):
        pairs.extend(platform.items())
    pairs.extend((k, v) for k, v in body.items() if isinstance(k, str))
    for key, val in pairs:
        if isinstance(key, str) and key.endswith("_nickname") \
           and isinstance(val, str) and val.strip():
            values.append(val.strip().strip("*"))
    return values


def graph_tags_for(contact_data: dict, tags: dict) -> List[str]:
    """联系人档案里挂的真实标签名（YAML trigger_tags + 正文指向标签文件的双链）。
    与 build_graph 的 contact_to_tags 同源，供 INDEX 单元格漂移核对复用。"""
    out = set()
    body = contact_data.get("yaml_body") or {}
    raw = (contact_data.get("frontmatter", {}).get("trigger_tags")
           or body.get("trigger_tags") or [])
    if isinstance(raw, str):
        raw = [raw]
    for t in raw:
        out.add(str(t).strip("[] ").strip())
    for link in contact_data.get("wiki_links", []):
        if link in tags:
            out.add(link)
    return sorted(t for t in out if t in tags)


def audit_index(contacts: dict, tags: dict, rosters: dict,
                index_text: Optional[str], issues: Issues) -> dict:
    """
    INDEX.md 自动对账（原手工审计清单 1–4 项的机械化）。

    联系人总览：行 ↔ 文件双向完整性；坏行（列数 ≠ 表头）单列报告；
    名单导航：行 ↔ 文件双向 + 计数格 vs 名单实际人数（本人除外）；
    标签导航：三层各自 行 ↔ 文件双向；INDEX 内全部 [[双链]] 可解析；
    提示：旧式纯文本伪标签行、检索列缺少已知昵称、有本人行但计数格未声明。
    """
    result: Dict[str, object] = {"parsed": index_text is not None}
    if index_text is None:
        issues.add("索引", ERR, "缺少 INDEX.md（无法对账）")
        return result

    idx = parse_index(index_text)
    valid_targets = set(contacts.keys()) | set(tags.keys()) | set(rosters.keys())

    # ── 联系人总览 ──
    if idx["overview_header"] is None:
        issues.add("索引", ERR, "INDEX.md 未找到「## 联系人总览」表格")
    rows = idx["overview_rows"]
    row_keys = {r["key"] for r in rows if r["key"]}
    for r in idx["overview_malformed"]:
        issues.add("索引", ERR,
                   f"联系人总览第 {r['line']} 行是坏行：{r['cells']} 个单元格 ≠ "
                   f"表头 {len(idx['overview_header'] or [])} 列（常见于两行误并成一行）",
                   line=r["line"])
    for r in rows:
        if r["key"] is None:
            issues.add("索引", ERR,
                       f"联系人总览第 {r['line']} 行链接列为空（无法定位档案）",
                       line=r["line"])
    for name in sorted(set(contacts.keys()) - row_keys):
        issues.add("索引", ERR, f"联系人 '{name}' 在 INDEX 总览没有有效行",
                   file=contacts[name].get("file_path"))
    for key in sorted(row_keys - set(contacts.keys())):
        issues.add("索引", ERR, f"INDEX 总览行 '[[{key}]]' 没有对应联系人档案",
                   file=contacts.get(key, {}).get("file_path"))
    # 伪标签 + 检索列 + 触发标签单元格漂移核对
    pseudo, search_missing, tag_cell_drift = [], [], []
    for r in rows:
        cell = r["tag_cell"]
        if cell and "[[" not in cell:
            pseudo.append({"line": r["line"], "key": r["key"] or "?"})
            issues.add("提示", HINT,
                       f"联系人总览第 {r['line']} 行（{r['key'] or '?'}）触发标签列是"
                       f"纯文本伪标签「{cell[:40]}…」——无对应标签文件，"
                       f"建议按 2c 迁移为 [[双链]]",
                       line=r["line"])
        # v1.3 单元格漂移：档案挂了真实标签，INDEX 触发标签格没同步 → 提示
        # 单向核对（档案是事实源，INDEX 是速查冗余）：只报 INDEX 缺，不报 INDEX 多。
        # 格子是纯文本伪标签时 tag_links 为空——已有专门提示，跳过漂移核对避免重复
        if r["key"] in contacts and r["tag_links"]:
            listed = set(r["tag_links"])
            archived = set(graph_tags_for(contacts[r["key"]], tags))
            behind = sorted(archived - listed)
            if behind:
                tag_cell_drift.append({"contact": r["key"], "missing": behind})
                issues.add("提示", HINT,
                           f"联系人 '{r['key']}' 的 INDEX 触发标签格落后于档案，"
                           f"缺 {''.join(f'[[{t}]]' for t in behind)}"
                           f"——档案已挂该标签，速查表未同步（单元格漂移）",
                           line=r["line"])
        if r["search_idx"] is not None and r["key"] in contacts:
            values = _contact_nickname_values(contacts[r["key"]])
            cell_flat = r["search_cell"].replace("**", "")
            gone = [v for v in values if v not in cell_flat]
            if values and gone:
                search_missing.append({"contact": r["key"], "missing": gone})
                issues.add("提示", HINT,
                           f"联系人 '{r['key']}' 的检索列（缩写·网名）没收录已知昵称："
                           f"{'、'.join(gone)}——群聊/聊天里这些名字无法 grep 命中",
                           line=r["line"])
    # 总览行的双链解析交由下方 INDEX 全量链接扫描统一报告（按目标去重）

    # ── 名单导航 ──
    nav_names = set()
    roster_counts = []
    for r in idx["roster_rows"]:
        nav_names.add(r["key"])
        if r["key"] not in rosters:
            issues.add("索引", ERR, f"名单导航行 '[[{r['key']}]]' 没有对应名单文件",
                       line=r["line"])
            continue
        actual = roster_stat_counts(rosters[r["key"]]["members"])
        if r["counts"] is None:
            issues.add("索引", ERR,
                       f"名单导航行 '{r['key']}' 计数格无法解析：「{r['count_cell']}」",
                       line=r["line"])
        else:
            exp = (actual["registered"], actual["roster_only"])
            if r["counts"] != exp:
                issues.add("索引", ERR,
                           f"名单导航 '{r['key']}' 计数过期：INDEX 写 "
                           f"{r['counts'][0]} 已登记 / {r['counts'][1]} 仅名单，"
                           f"名单文件实际 {exp[0]} / {exp[1]}"
                           + (f"（另含本人 {actual['self']}）" if actual["self"] else ""),
                           line=r["line"])
        if actual["self"] > 0 and not r["mentions_self"]:
            issues.add("提示", HINT,
                       f"名单 '{r['key']}' 有 {actual['self']} 个「本人」行，"
                       f"但计数格未声明（建议「N 已登记 / M 仅名单（另含本人）」）",
                       line=r["line"])
        roster_counts.append({"roster": r["key"],
                              "index": list(r["counts"]) if r["counts"] else None,
                              "actual": [actual["registered"], actual["roster_only"], actual["self"]],
                              "match": (r["counts"] == (actual["registered"], actual["roster_only"]))})
    for name in sorted(set(rosters.keys()) - nav_names):
        issues.add("索引", ERR, f"名单 '{name}' 没有 INDEX 导航行",
                   file=rosters[name].get("file_path"))

    # ── 标签导航（三层） ──
    tag_nav_summary = {}
    type_map = {"school": "学校", "field": "专业方向", "city": "城市"}
    for layer, rows_ in idx["tag_nav"].items():
        keys = {r["key"] for r in rows_}
        files = {t for t, d in tags.items() if d.get("type") == layer}
        missing_rows = sorted(files - keys)
        nav_only = sorted(keys - files)
        for k in nav_only:
            if k in tags:
                issues.add("提示", HINT,
                           f"标签导航「{type_map[layer]}」层列了 [[{k}]]，"
                           f"但它实际在 tags/{tags[k]['type']}/ 层（层级不符）")
            elif k not in valid_targets:
                pass  # 已在断链检查报出
            else:
                issues.add("索引", ERR, f"标签导航行 '{k}' 没有对应标签文件")
        for t in missing_rows:
            issues.add("索引", ERR,
                       f"标签 '{t}'（tags/{layer}/）没有 INDEX「{type_map[layer]}」导航行",
                       file=tags[t].get("file_path"))
        tag_nav_summary[layer] = {"missing_rows": missing_rows, "unlisted_files": nav_only}

    # ── INDEX 全量双链 ──
    broken = [l for l in idx["all_links"]
              if l not in valid_targets and l not in PLACEHOLDER_LINKS]
    for link in sorted(set(broken)):
        issues.add("断链", ERR, f"INDEX.md 中的 [[{link}]] 找不到对应文件")

    result.update({
        "rows": len(rows),
        "files": len(contacts),
        "malformed_rows": idx["overview_malformed"],
        "missing_contacts": sorted(set(contacts.keys()) - row_keys),
        "extra_rows": sorted(row_keys - set(contacts.keys())),
        "pseudo_tag_rows": pseudo,
        "roster_counts": roster_counts,
        "tag_nav": tag_nav_summary,
        "broken_links": sorted(set(broken)),
        "search_cell_missing": search_missing,
        "tag_cell_drift": tag_cell_drift,
    })
    return result


def roster_stat_counts(members: List[dict]) -> dict:
    return {
        "registered": sum(1 for m in members if m["status"] == "已登记"),
        "roster_only": sum(1 for m in members if m["status"] == "仅名单"),
        "self": sum(1 for m in members if m["status"] == "本人"),
        "invalid": sum(1 for m in members if m["status"] not in ROSTER_STATUSES),
    }


# ─── 第 7 部分：schema / 碰撞 / last_contact ────────────────────────────────

def audit_schema(contacts: dict, issues: Issues) -> dict:
    """
    联系人 YAML schema 校验（只针对 contacts/）。

    错误级：YAML 解析失败（整块字段失踪，必须修）。
    提示级：未知顶层键（迁移建议）、
    昵称只在注释/other/子键缺失、ID 值内嵌昵称注释、缺 frontmatter、重复备注节。
    strength 是自由词——本函数不校验它。
    """
    summary = {"yaml_errors": [], "unknown_keys": [],
               "annotated_ids": [], "nickname_mentions": [],
               "no_frontmatter": [], "duplicate_sections": []}

    for name, data in contacts.items():
        path = data.get("file_path")
        for err_msg in data["yaml_errors"]:
            issues.add("schema", ERR, f"联系人 '{name}' {err_msg}", file=path)
            summary["yaml_errors"].append({"contact": name, "error": err_msg})

        body = data["yaml_body"]
        if body:
            for key in body.keys():
                if key in CANONICAL_KEYS:
                    continue
                suggestion = UNKNOWN_KEY_SUGGESTION.get(
                    key, "并入 platform 子键或正文小节")
                issues.add("提示", HINT,
                           f"联系人 '{name}' 有非规范顶层键 `{key}:`"
                           f"→ {suggestion}",
                           file=path)
                summary["unknown_keys"].append({"contact": name, "key": key})

            # 昵称子键覆盖检查：platform.*_nickname 之外，昵称散落在
            # YAML 注释 / platform.other 文案 / ID 值括号注释里 → 提示
            platform = body.get("platform") or {}
            if isinstance(platform, dict):
                for pkey, pval in platform.items():
                    if not isinstance(pval, str):
                        continue
                    if pkey in ID_SUBKEYS and "（" in pval and re.search(r"（[^）]*昵称", pval):
                        issues.add("提示", HINT,
                                   f"联系人 '{name}' 的 `{pkey}:` 值内嵌了昵称注释"
                                   f"（{pval[:36]}…）——号码应保持纯值，"
                                   f"昵称放 `{pkey}_nickname` 子键",
                                   file=path)
                        summary["annotated_ids"].append({"contact": name, "key": pkey})
                    if pkey in ("other", "nicknames") and re.search(r"昵称|QQ ?名|微信名|网名|小号", pval):
                        if "微信" in pval:
                            sug = "wechat_nickname"
                        elif re.search(r"QQ|qq", pval):
                            sug = "qq_nickname"
                        else:
                            sug = "对应平台的 *_nickname"
                        issues.add("提示", HINT,
                                   f"联系人 '{name}' 的昵称写在 `platform.{pkey}` 文案里"
                                   f"——聊天记录按昵称 grep 时不可靠，"
                                   f"建议拆成 `{sug}` 子键（值保持纯昵称，注释另放）",
                                   file=path)
                        summary["nickname_mentions"].append({"contact": name, "where": f"platform.{pkey}"})
            m = re.search(r"^```yaml\n(.*?)\n```", data["text"], re.DOTALL | re.MULTILINE)
            if m:
                for line in m.group(1).splitlines():
                    key_part, _, comment = line.partition("#")
                    if "_nickname" in key_part or re.match(r"^\s*nicknames\s*:", key_part):
                        continue  # 昵称已落在子键上，注释只是补充说明
                    if comment and re.search(r"昵称|QQ ?名|微信名", comment):
                        issues.add("提示", HINT,
                                   f"联系人 '{name}' 的昵称只写在 YAML 注释里"
                                   f"——聊天记录按昵称 grep 认不出，"
                                   f"应落成 platform.*_nickname 子键",
                                   file=path)
                        summary["nickname_mentions"].append({"contact": name, "where": "yaml 注释"})
                        break

        # 以下两项不依赖 pyyaml（frontmatter 有正则降级解析；小节标题是纯文本）——
        # 降级模式下照常执行
        if not data["frontmatter"] or "type" not in data["frontmatter"]:
            issues.add("提示", HINT,
                       f"联系人 '{name}' 缺 frontmatter（约定 title + type: contact）",
                       file=path)
            summary["no_frontmatter"].append({"contact": name})

        notes = [h for h in data["body_headings"] if "备注" in h]
        if len(notes) > 1:
            issues.add("提示", HINT,
                           f"联系人 '{name}' 有多个备注类小节（{'、'.join(notes)}）"
                           f"——教训与口径应合并进唯一的「## 备注」",
                           file=path)
            summary["duplicate_sections"].append({"contact": name, "headings": notes})
    return summary


def audit_collisions(contacts: dict, issues: Issues) -> List[dict]:
    """
    平台账号跨文件碰撞：同一 ID 子键的同一值出现在 ≥2 个联系人 → [冲突] 错误。

    归一化：剥掉（…）/(…) 注释再比对。排除 other / nicknames / *_nickname
    （自由文案字段）；同一文件内 student_id==bupt 或 email==QQ号@qq.com
    这类交叉引用不算冲突。
    """
    def normalize(v: str) -> str:
        v = re.sub(r"（[^）]*）", "", v)
        v = re.sub(r"\([^)]*\)", "", v)
        return v.strip()

    by_key: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    for name, data in contacts.items():
        body = data.get("yaml_body") or {}
        platform = body.get("platform") or {}
        if not isinstance(platform, dict):
            continue
        for pkey, pval in platform.items():
            if pkey not in ID_SUBKEYS or not isinstance(pval, str):
                continue
            val = normalize(pval)
            if val and not re.fullmatch(r"[-—\s]*", val):
                by_key[(pkey, val)].append(name)

    collisions = []
    for (pkey, val), names in sorted(by_key.items()):
        if len(names) >= 2:
            collisions.append({"key": pkey, "value": val, "contacts": sorted(names)})
            issues.add("冲突", ERR,
                       f"平台 `{pkey}` 值「{val}」同时出现在 {'、'.join(sorted(names))}"
                       f"——按 2b 冲突处理流程确认是同一人（合并）还是登记错误（修正）")
    return collisions


_DATE_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(.*)$", re.S)


def audit_last_contact(contacts: dict, issues: Issues,
                       today: datetime.date, stale_days: int) -> dict:
    """
    last_contact 格式与陈旧度。

    规范形：`YYYY-MM-DD` 或 `YYYY-MM-DD（全角括号注释）`。
    - 空 / `""` / `—` / `-` / 键缺失 → [提示] 空值
    - 日期后跟空格或半角括号注释 → [提示] 建议规范为全角括号
    - 无合法 ISO 日期前缀（如 "everyday"）或未来日期 / 非法日期 → [格式] 错误
    - 距 last_contact 超过 stale_days 天 → [提示] 陈旧
    只报告，**绝不**替用户编造或改动日期。
    """
    summary = {"empty": [], "invalid": [], "nonstandard": [], "stale": []}
    if not HAS_YAML:
        return summary  # 降级：字段不可见，整类跳过（由 run_audit 的降级提示统一声明）
    for name, data in contacts.items():
        if data.get("yaml_errors"):
            continue  # 整块字段未入库（已有 [schema] 错误），不再产生误导性空值提示
        body = data.get("yaml_body") or {}
        val = body.get("last_contact")
        if val is None:
            summary["empty"].append(name)
            issues.add("提示", HINT,
                       f"联系人 '{name}' 没有 last_contact 字段（最近一次有意义互动）",
                       file=data.get("file_path"))
            continue
        if isinstance(val, datetime.date):
            d = val
        else:
            s = str(val).strip()
            if s in ("", "—", "-", "–"):
                summary["empty"].append(name)
                issues.add("提示", HINT,
                           f"联系人 '{name}' 的 last_contact 是空值/占位符「{s or '（空）'}」",
                           file=data.get("file_path"))
                continue
            m = _DATE_RE.match(s)
            if not m:
                summary["invalid"].append({"contact": name, "value": s})
                issues.add("格式", ERR,
                           f"联系人 '{name}' 的 last_contact「{s}」不是日期——"
                           f"规范形 YYYY-MM-DD（可选全角括号注释）；未知就留空",
                           file=data.get("file_path"))
                continue
            try:
                d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                summary["invalid"].append({"contact": name, "value": s})
                issues.add("格式", ERR,
                           f"联系人 '{name}' 的 last_contact「{s}」日期值非法",
                           file=data.get("file_path"))
                continue
            rest = m.group(4).strip()
            if rest and not (rest.startswith("（") and rest.endswith("）")):
                summary["nonstandard"].append({"contact": name, "value": s})
                issues.add("提示", HINT,
                           f"联系人 '{name}' 的 last_contact「{s}」建议规范化为"
                           f"「{str(d)}（{rest}）」（全角括号注释）",
                           file=data.get("file_path"))
        if d > today:
            summary["invalid"].append({"contact": name, "value": str(d)})
            issues.add("格式", ERR,
                       f"联系人 '{name}' 的 last_contact {d} 是未来日期",
                       file=data.get("file_path"))
            continue
        age = (today - d).days
        if age > stale_days:
            summary["stale"].append({"contact": name, "date": str(d), "days": age})
            issues.add("提示", HINT,
                       f"联系人 '{name}' 已 {age} 天未联系（last_contact={d}，阈值 {stale_days} 天）",
                       file=data.get("file_path"))
    return summary


# ─── 第 8 部分：冗余边检测 ──────────────────────────────────────────────────

def find_redundant_edges(graph: dict, tags: dict) -> List[dict]:
    """
    识别"仅共享联系人而相关"的标签对。

    规则：
      - 两个标签有直接 [[双链]]（结构边）→ 保留
      - 学校↔城市 视为合法结构边
      - 其余仅靠共享联系人间接相连 → 冗余候选（人工复核）
    """
    redundant = []
    for edge_key, shared_contacts in graph["contact_bridged_edges"].items():
        a, b = eval(edge_key)  # safe: we built these keys ourselves
        is_structural = (a, b) in graph["structural_edges"]
        a_type = tags.get(a, {}).get("type", "unknown")
        b_type = tags.get(b, {}).get("type", "unknown")
        school_city = {a_type, b_type} == {"school", "city"}
        if not is_structural and not school_city:
            redundant.append({
                "tag_a": a,
                "tag_b": b,
                "tag_a_type": a_type,
                "tag_b_type": b_type,
                "shared_contacts": shared_contacts,
                "mesh_node": shared_contacts[0] if len(shared_contacts) == 1 else None,
                "reason": "仅通过共享联系人间接相连，建议删除此边或让用户确认为结构边",
            })
    return redundant


# ─── 第 9 部分：报告生成 ────────────────────────────────────────────────────

def generate_report(vault_path: str, contacts: dict, tags: dict, graph: dict,
                    issues: Issues, redundant: List[dict], rosters: dict,
                    membership: dict, index_result: dict) -> str:
    """完整人类可读报告（--report）。"""
    rosters = rosters or {}
    r = []
    r.append("=" * 60)
    r.append(f"知识图谱审计报告 — {vault_path}")
    r.append("=" * 60)

    r.append("\n## 基本统计")
    r.append(f"  联系人数量: {len(contacts)}")
    r.append(f"  标签数量:   {len(tags)}")
    tag_types = defaultdict(int)
    for t in tags.values():
        tag_types[t.get("type", "unknown")] += 1
    for ttype, cnt in sorted(tag_types.items()):
        r.append(f"    - {ttype}: {cnt} 个")
    r.append(f"  Wiki-links 总数: {sum(len(d['wiki_links']) for d in contacts.values())}")
    r.append(f"  名单数量: {len(rosters)}")
    for roster_name, roster_data in sorted(rosters.items()):
        c = roster_stat_counts(roster_data["members"])
        extra = f" + 本人 {c['self']}" if c["self"] else ""
        r.append(f"    - {roster_name}: 已登记 {c['registered']} + 仅名单 {c['roster_only']}{extra}")

    r.append(f"\n## INDEX 对账")
    if not index_result.get("parsed"):
        r.append("  （无 INDEX.md）")
    else:
        r.append(f"  总览行 {index_result.get('rows', 0)} / 档案 {index_result.get('files', 0)}"
                 f"；坏行 {len(index_result.get('malformed_rows', []))}"
                 f"；伪标签提示行 {len(index_result.get('pseudo_tag_rows', []))}"
                 f"；触发标签格漂移 {len(index_result.get('tag_cell_drift', []))}")
        for rc in index_result.get("roster_counts", []):
            mark = "✅" if rc["match"] else "❌"
            r.append(f"  [{mark}] {rc['roster']}: INDEX {rc['index']} vs 实际 {rc['actual'][:2]}（本人 {rc['actual'][2]}）")

    r.append(f"\n## 标签页成员核对")
    r.append(f"  正向缺口（联系人有标签、页上没列）: {len(membership['missing'])}")
    tag_group: Dict[str, List[str]] = defaultdict(list)
    for p in membership["missing"]:
        tag_group[p["tag"]].append(p["contact"])
    for tag, names in sorted(tag_group.items(), key=lambda x: -len(x[1])):
        r.append(f"    - {tag}: 缺 {len(names)} 人 — {', '.join(names[:6])}"
                 + ("…" if len(names) > 6 else ""))
    r.append(f"  反向漂移（页上列了但没挂标签/非联系人）: {len(membership['reverse'])}")
    for p in membership["reverse"]:
        r.append(f"    - {p['tag']} ← {p['name']}（{p['reason']}）")
    r.append(f"  无成员节（hub 页，跳过）: {len(membership['skipped_tags'])} 个")

    r.append("\n## 标签使用排行（按引用联系人数量）")
    ranked = sorted(graph["tag_to_contacts"].items(), key=lambda x: -len(x[1]))
    for tag_name, contact_list in ranked[:15]:
        r.append(f"  {tag_name}: {len(contact_list)} 人 — {', '.join(contact_list[:3])}")
        if len(contact_list) > 3:
            r.append(f"    ...还有 {len(contact_list) - 3} 人")

    r.append("\n## 联系人圈层分析")
    for name in sorted(contacts.keys()):
        my_tags = graph["contact_to_tags"].get(name, [])
        tag_type_map = {}
        for t in my_tags:
            ttype = tags.get(t, {}).get("type", "?")
            tag_type_map.setdefault(ttype, []).append(t)
        tag_summary = " | ".join(
            f"{ttype}: {', '.join(ts)}" for ttype, ts in sorted(tag_type_map.items()))
        r.append(f"  [{name}] → {tag_summary}")

    r.append(f"\n## 标签间结构边（{len(graph['structural_edges'])} 条）")
    for a, b in graph["structural_edges"]:
        r.append(f"  {a} ({tags.get(a, {}).get('type', '?')}) ↔ {b} ({tags.get(b, {}).get('type', '?')})")

    r.append(f"\n## 仅通过联系人桥接的标签对（{len(redundant)} 个，冗余候选）")
    if redundant:
        for x in redundant:
            mesh = f" (桥: {x['mesh_node']})" if x["mesh_node"] else ""
            r.append(f"  {x['tag_a']} ({x['tag_a_type']}) — {x['tag_b']} ({x['tag_b_type']})"
                     f"  ← 共享: {', '.join(x['shared_contacts'])}{mesh}")
    else:
        r.append("  （无冗余边，图谱结构健康）")

    r.append(f"\n## 错误（{issues.count(severity=ERR)} 个）")
    for e in issues.errors():
        r.append(f"  {e}")
    if issues.count(severity=ERR) == 0:
        r.append("  ✅ 无错误级问题")

    r.append(f"\n## 提示（{issues.count(severity=HINT)} 个，人工分诊：迁移/陈旧/升级类，不判失败）")
    for h in issues.hints():
        r.append(f"  {h}")

    return "\n".join(r)


def generate_summary(vault_path: str, contacts: dict, tags: dict, rosters: dict,
                     issues: Issues, redundant: List[dict]) -> str:
    """默认紧凑摘要：统计 + 各类计数 + 全部错误 + 提示计数。"""
    r = []
    r.append(f"审计摘要 — {vault_path}"
             + ("　【⚠ 降级模式：无 pyyaml，YAML 相关检查已跳过】" if not HAS_YAML else ""))
    c = defaultdict(int)
    for i in issues.detail:
        c[f"{i['category']}/{i['severity']}"] += 1
    r.append(f"联系人 {len(contacts)} · 标签 {len(tags)} · 名单 {len(rosters)}"
             f" · 错误 {issues.count(severity=ERR)} · 提示 {issues.count(severity=HINT)}"
             f" · 冗余边候选 {len(redundant)}")
    if c:
        r.append("各类计数：" + " · ".join(f"{k}={v}" for k, v in sorted(c.items())))
    errs = issues.errors()
    if errs:
        r.append("")
        r.append(f"错误（{len(errs)}）：")
        r.extend(f"  {e}" for e in errs)
    else:
        r.append("\n✅ 无错误级问题")
    r.append("\n提示详情与完整分析：--report；机器可读：--json")
    return "\n".join(r)


# ─── 第 10 部分：主入口 ─────────────────────────────────────────────────────

def run_audit(vault_path: str, stale_days: int = 90,
              today: Optional[datetime.date] = None) -> dict:
    """执行全部扫描与检查，返回结构化结果（供 main 与测试复用）。"""
    today = today or datetime.date.today()
    contacts, tags, rosters, index_text = scan_vault(vault_path)
    graph = build_graph(contacts, tags)

    issues = Issues()
    audit_integrity(contacts, tags, graph, rosters, issues)
    membership = audit_membership(contacts, tags, graph, issues)
    index_result = audit_index(contacts, tags, rosters, index_text, issues)
    schema = audit_schema(contacts, issues)
    collisions = audit_collisions(contacts, issues)
    last_contact = audit_last_contact(contacts, issues, today, stale_days)
    redundant = find_redundant_edges(graph, tags)

    if not HAS_YAML:
        issues.add("schema", HINT,
                   "降级模式（pyyaml 未安装）：已跳过依赖 YAML 的检查——"
                   "schema/杂键、平台 ID 碰撞、last_contact 格式与陈旧、"
                   "检索列昵称核对；断链/孤立/名单/INDEX/标签页检查照常。"
                   "完整检查请装 pyyaml：python -m pip install pyyaml"
                   "（建议虚拟环境，勿装进系统解释器）")

    return {
        "vault_path": vault_path,
        "today": str(today),
        "stale_days": stale_days,
        "contacts": contacts,
        "tags": tags,
        "rosters": rosters,
        "graph": graph,
        "issues": issues,
        "membership": membership,
        "index": index_result,
        "schema": schema,
        "collisions": collisions,
        "last_contact": last_contact,
        "redundant": redundant,
    }


def to_json(result: dict) -> dict:
    issues: Issues = result["issues"]
    membership = result["membership"]
    stats = {
        "contacts": len(result["contacts"]),
        "tags": len(result["tags"]),
        "rosters": len(result["rosters"]),
        "errors": issues.count(severity=ERR),
        "hints": issues.count(severity=HINT),
        "redundant_edges": len(result["redundant"]),
        "index_rows": result["index"].get("rows", 0),
        "index_malformed": len(result["index"].get("malformed_rows", [])),
        "pseudo_tag_rows": len(result["index"].get("pseudo_tag_rows", [])),
        "tag_cell_drift": len(result["index"].get("tag_cell_drift", [])),
        "membership_missing": len(membership["missing"]),
        "membership_reverse": len(membership["reverse"]),
        "membership_skipped": len(membership["skipped_tags"]),
        "yaml_errors": len(result["schema"]["yaml_errors"]),
        "unknown_keys": len(result["schema"]["unknown_keys"]),
        "id_collisions": len(result["collisions"]),
        "last_contact_empty": len(result["last_contact"]["empty"]),
        "last_contact_invalid": len(result["last_contact"]["invalid"]),
        "last_contact_stale": len(result["last_contact"]["stale"]),
    }
    return {
        "schema_version": 2,
        "degraded": not HAS_YAML,
        "vault": result["vault_path"],
        "generated": result["today"],
        "stale_days": result["stale_days"],
        "stats": stats,
        "errors": issues.errors(),
        "hints": issues.hints(),
        "issues_detail": issues.detail,
        "index": result["index"],
        "membership": membership,
        "schema": result["schema"],
        "collisions": result["collisions"],
        "last_contact": result["last_contact"],
        "graph": result["graph"],
        "redundant_edges": result["redundant"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="人际关系图谱审计（详见模块 docstring）",
        usage="python audit_graph.py <vault_path> [--report] [--json] [--strict] [--stale-days N]")
    parser.add_argument("vault_path", help="vault 根目录（如 ~/people）")
    parser.add_argument("--report", action="store_true",
                        help="输出完整人类可读报告（默认为紧凑摘要）")
    parser.add_argument("--json", action="store_true", dest="output_json",
                        help="输出机器可读 JSON（schema_version 2；进度走 stderr）")
    parser.add_argument("--strict", action="store_true",
                        help="存在错误级问题时以退出码 1 结束（提示级永不失败）")
    parser.add_argument("--stale-days", type=int, default=90, dest="stale_days",
                        help="last_contact 陈旧度阈值天数（默认 90）")
    args = parser.parse_args(argv)

    vault_path = os.path.expanduser(args.vault_path)
    if not os.path.isdir(vault_path):
        eprint(f"错误: 路径不存在 — {vault_path}")
        return 2

    if not HAS_YAML:
        eprint("⚠ pyyaml 未安装：进入降级模式（仅结构审计，YAML 相关检查跳过）。"
               " 安装：python -m venv .venv && .venv/Scripts/pip install pyyaml"
               "（Unix 用 .venv/bin/pip）")
        if args.strict:
            eprint("错误: --strict 要求完整检查覆盖，降级模式不可用作门禁——安装 pyyaml 后重试。")
            return 2

    eprint(f"🔍 扫描 vault: {vault_path}")
    result = run_audit(vault_path, stale_days=args.stale_days)
    issues: Issues = result["issues"]
    eprint(f"   联系人 {len(result['contacts'])} · 标签 {len(result['tags'])} · 名单 {len(result['rosters'])}")
    eprint("🔬 检查完成")

    if args.output_json:
        print(json.dumps(to_json(result), ensure_ascii=False, indent=2))
    elif args.report:
        print(generate_report(vault_path, result["contacts"], result["tags"],
                              result["graph"], issues, result["redundant"],
                              result["rosters"], result["membership"],
                              result["index"]))
    else:
        print(generate_summary(vault_path, result["contacts"], result["tags"],
                               result["rosters"], issues, result["redundant"]))

    if issues.count(severity=ERR) and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

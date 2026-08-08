"""
人际关系图谱审计脚本
=====================

用于 Obsidian vault 中联系人知识图谱的完整性校验和结构分析。

核心功能：
  1. 解析 Markdown 文件中的 [[wiki-links]] 双向链接
  2. 提取 YAML frontmatter 中的结构化字段
  3. 构建图结构（联系人 ↔ 标签 的多层网络）
  4. 检测断链、孤立节点
  5. 识别"仅共享联系人而相关的冗余标签边"
  6. 按圈层（学校/方向/城市）分组可视化分析

用法：
  python audit_graph.py <vault_path> [--report] [--fix]
"""

import os
import re
import sys
import json
import yaml
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional


# ─── 第 1 部分：Wiki-Link 解析器 ───────────────────────────────────────────

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
    # 正则：匹配 [[...]] ，内部捕获到 | 或 # 之前的部分
    pattern = r'\[\[([^\]|#]+)(?:[|#][^\]]+)?\]\]'
    matches = re.findall(pattern, text)
    # 去重并保持顺序
    seen = set()
    result = []
    for m in matches:
        target = m.strip()
        if target and target not in seen:
            seen.add(target)
            result.append(target)
    return result


def parse_frontmatter(text: str) -> dict:
    """
    从 Markdown 文本中提取 YAML frontmatter。

    返回 dict，解析失败返回 {}。
    """
    # frontmatter 在 --- 分隔线之间
    match = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
    if not match:
        return {}
    try:
        return yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}


# ─── 第 2 部分：文件扫描器 ─────────────────────────────────────────────────

def scan_vault(vault_path: str) -> Tuple[Dict[str, dict], Dict[str, dict]]:
    """
    扫描整个 vault，返回 (联系人数据, 标签数据)。

    联系人数据：{文件名（不含扩展名）: {frontmatter, wiki_links, file_path}}
    标签数据：  {标签名: {frontmatter, linked_contacts, file_path}}
    """
    vault = Path(vault_path)
    contacts = {}
    tags = {}

    # ── 扫描 contacts/ 目录 ──
    contacts_dir = vault / "contacts"
    if contacts_dir.exists():
        for md_file in contacts_dir.glob("*.md"):
            text = md_file.read_text(encoding="utf-8")
            fm = parse_frontmatter(text)
            links = parse_wiki_links(text)
            name = md_file.stem  # 文件名即联系人名
            contacts[name] = {
                "frontmatter": fm,
                "wiki_links": links,
                "file_path": str(md_file),
            }

    # ── 扫描 tags/ 子目录 ──
    tags_dir = vault / "tags"
    if tags_dir.exists():
        for md_file in tags_dir.rglob("*.md"):
            text = md_file.read_text(encoding="utf-8")
            fm = parse_frontmatter(text)
            links = parse_wiki_links(text)
            name = md_file.stem
            # 判断标签类型：由所在子目录决定
            tag_type = "unknown"
            rel = md_file.relative_to(tags_dir)
            tag_type = rel.parts[0] if len(rel.parts) > 1 else "root"
            tags[name] = {
                "frontmatter": fm,
                "wiki_links": links,
                "type": tag_type,
                "linked_contacts": [],
                "linked_tags": [],
                "file_path": str(md_file),
            }

    return contacts, tags


# ─── 第 3 部分：图结构构建 ──────────────────────────────────────────────────

def build_graph(contacts: dict, tags: dict) -> dict:
    """
    构建知识图谱结构。

    返回：
    {
      "nodes": {
        "contact:<name>": {"type": "contact", "data": ...},
        "tag:<name>":    {"type": "tag", "tag_type": "school", "data": ...},
      },
      "edges": {
        "contact-tag": [(contact, tag), ...],   # 联系人→标签
        "tag-tag":     [(tag_a, tag_b), ...],   # 标签→标签（结构边）
        "tag-tag-via-contact": [(tag_a, tag_b, [contacts]), ...],  # 仅通过联系人相连的标签
      }
    }
    """

    # Step 1: 建立联系人→标签的映射
    contact_to_tags: Dict[str, Set[str]] = {}
    for name, data in contacts.items():
        # 从 frontmatter 的 trigger_tags 字段拿标签
        raw_tags = data["frontmatter"].get("trigger_tags", [])
        tag_set = set()
        for t in raw_tags:
            # 可能是纯字符串 或 [[string]]
            t_str = str(t).strip("[] ").strip()
            tag_set.add(t_str)
        # 也从正文 wiki-links 中提取，交叉验证
        wiki_links = data["wiki_links"]
        # 过滤掉非标签的链接（比如链向其他联系人的）
        for link in wiki_links:
            if link in tags:
                tag_set.add(link)

        contact_to_tags[name] = tag_set

    # Step 2: 建立标签→联系人的反向映射
    tag_to_contacts: Dict[str, Set[str]] = defaultdict(set)
    for contact_name, tag_set in contact_to_tags.items():
        for tag in tag_set:
            if tag in tags:
                tag_to_contacts[tag].add(contact_name)

    # Step 3: 建立标签→标签的边（从标签文件自身的 wiki-links 中找）
    tag_to_tags: Dict[str, Set[str]] = {}
    for tag_name, tag_data in tags.items():
        linked = set()
        for link in tag_data["wiki_links"]:
            if link in tags and link != tag_name:
                linked.add(link)
        tag_to_tags[tag_name] = linked

    # Step 4: 识别"仅通过联系人相连"的标签对
    # 如果标签 A 和 B 之间没有直接的 [[双链]]，但它们共享联系人，则是"间接连接"
    structural_edges = set()
    contact_bridged_edges: Dict[Tuple[str, str], Set[str]] = defaultdict(set)

    all_tags = list(tags.keys())
    for i in range(len(all_tags)):
        for j in range(i + 1, len(all_tags)):
            a, b = all_tags[i], all_tags[j]
            # 检查是否有直接结构边
            if a in tag_to_tags.get(b, set()) or b in tag_to_tags.get(a, set()):
                structural_edges.add((a, b))
            # 检查共享联系人
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


# ─── 第 4 部分：完整性校验 ──────────────────────────────────────────────────

def audit_integrity(contacts: dict, tags: dict, graph: dict) -> List[str]:
    """
    校验知识图谱的完整性，返回问题列表。

    检查项：
      1. 所有联系人文件中的 [[链接]] 是否都有对应文件
      2. 所有标签文件中的 [[链接]] 是否都有对应文件
      3. 是否存在孤立联系人（没有链接到任何标签）
      4. 是否存在孤立标签（没有任何联系人引用它）
    """
    issues = []

    all_valid_targets = set(contacts.keys()) | set(tags.keys())

    # ── 检查联系人的出链 ──
    for name, data in contacts.items():
        for link in data["wiki_links"]:
            if link not in all_valid_targets:
                # 忽略模板示例中的特殊链接
                if link in ("双链", "tag-name", "双链示例"):
                    continue
                issues.append(
                    f"[断链] 联系人 '{name}' 中的 [[{link}]] 找不到对应文件"
                )

    # ── 检查标签的出链 ──
    for tag_name, tag_data in tags.items():
        for link in tag_data["wiki_links"]:
            if link not in all_valid_targets:
                if link in ("双链", "tag-name", "双链示例"):
                    continue
                issues.append(
                    f"[断链] 标签 '{tag_name}' 中的 [[{link}]] 找不到对应文件"
                )

    # ── 检查孤立联系人 ──
    for name, data in contacts.items():
        if not data["wiki_links"]:
            issues.append(f"[孤立] 联系人 '{name}' 没有任何 wiki-links")

    # ── 检查孤立标签 ──
    for tag_name in tags:
        if tag_name not in graph["tag_to_contacts"] or not graph["tag_to_contacts"][tag_name]:
            issues.append(f"[孤立] 标签 '{tag_name}' 没有被任何联系人引用")

    return issues


# ─── 第 5 部分：冗余边检测 ──────────────────────────────────────────────────

def find_redundant_edges(graph: dict, tags: dict) -> List[dict]:
    """
    识别"仅共享联系人而相关"的标签对

    规则：
      - 如果两个标签有直接的 [[双链]]（结构边），保留
      - 如果两个标签仅因为共享联系人而被间接连接，标记为冗余候选
      - 学校↔城市 总是结构边（建议保留）
      - 同体系方向（如 OI↔ICPC）保留
    """

    redundant = []

    for edge_key, shared_contacts in graph["contact_bridged_edges"].items():
        # edge_key 是 "(tag_a, tag_b)" 字符串，解析回来
        a, b = eval(edge_key)  # safe here: we built these keys ourselves

        # 检查是否是结构边（已在标签文件中显式双链）
        is_structural = (a, b) in graph["structural_edges"]

        # 检查是否相同类型（同体系可保留）
        a_type = tags.get(a, {}).get("type", "unknown")
        b_type = tags.get(b, {}).get("type", "unknown")

        # 学校↔城市 是合法结构边
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


# ─── 第 6 部分：报告生成 ────────────────────────────────────────────────────

def generate_report(
    vault_path: str,
    contacts: dict,
    tags: dict,
    graph: dict,
    issues: List[str],
    redundant: List[dict],
):
    """生成人类可读的审计报告。"""

    report = []
    report.append("=" * 60)
    report.append(f"知识图谱审计报告 — {vault_path}")
    report.append("=" * 60)

    # ── 基本统计 ──
    report.append(f"\n## 基本统计")
    report.append(f"  联系人数量: {len(contacts)}")
    report.append(f"  标签数量:   {len(tags)}")
    tag_types = defaultdict(int)
    for t in tags.values():
        tag_types[t.get("type", "unknown")] += 1
    for ttype, cnt in sorted(tag_types.items()):
        report.append(f"    - {ttype}: {cnt} 个")

    total_wiki_links = sum(len(d["wiki_links"]) for d in contacts.values())
    report.append(f"  Wiki-links 总数: {total_wiki_links}")

    # ── 标签使用排行 ──
    report.append(f"\n## 标签使用排行（按引用联系人数量）")
    ranked = sorted(graph["tag_to_contacts"].items(), key=lambda x: -len(x[1]))
    for tag_name, contact_list in ranked[:15]:
        report.append(f"  {tag_name}: {len(contact_list)} 人 — {', '.join(contact_list[:3])}")
        if len(contact_list) > 3:
            report.append(f"    ...还有 {len(contact_list) - 3} 人")

    # ── 联系人圈层分析 ──
    report.append(f"\n## 联系人圈层分析")
    for name in sorted(contacts.keys()):
        my_tags = graph["contact_to_tags"].get(name, [])
        tag_type_map = {}
        for t in my_tags:
            ttype = tags.get(t, {}).get("type", "?")
            tag_type_map.setdefault(ttype, []).append(t)
        tag_summary = " | ".join(
            f"{ttype}: {', '.join(ts)}" for ttype, ts in sorted(tag_type_map.items())
        )
        report.append(f"  [{name}] → {tag_summary}")

    # ── 结构边 ──
    report.append(f"\n## 标签间结构边（{len(graph['structural_edges'])} 条）")
    for a, b in graph["structural_edges"]:
        a_type = tags.get(a, {}).get("type", "?")
        b_type = tags.get(b, {}).get("type", "?")
        report.append(f"  {a} ({a_type}) ↔ {b} ({b_type})")

    # ── 冗余边候选 ──
    report.append(f"\n## 仅通过联系人桥接的标签对（{len(redundant)} 个，冗余候选）")
    if redundant:
        for r in redundant:
            c_str = ", ".join(r["shared_contacts"])
            mesh_info = f" (桥: {r['mesh_node']})" if r["mesh_node"] else ""
            report.append(
                f"  {r['tag_a']} ({r['tag_a_type']}) — {r['tag_b']} ({r['tag_b_type']})"
                f"  ← 共享: {c_str}{mesh_info}"
            )
    else:
        report.append("  （无冗余边，图谱结构健康）")

    # ── 完整性问题 ──
    report.append(f"\n## 完整性检查（{len(issues)} 个问题）")
    if issues:
        for issue in issues:
            report.append(f"  {issue}")
    else:
        report.append("  ✅ 所有链接有效，无断链、无孤立节点")

    return "\n".join(report)


# ─── 第 7 部分：主入口 ──────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("用法: python audit_graph.py <vault_path> [--report] [--json]")
        print("示例: python audit_graph.py D:/people --report")
        sys.exit(1)

    vault_path = sys.argv[1]
    show_report = "--report" in sys.argv
    output_json = "--json" in sys.argv

    if not os.path.isdir(vault_path):
        print(f"错误: 路径不存在 — {vault_path}")
        sys.exit(1)

    # Step 1: 扫描
    print(f"🔍 扫描 vault: {vault_path}")
    contacts, tags = scan_vault(vault_path)
    print(f"   找到 {len(contacts)} 个联系人, {len(tags)} 个标签")

    # Step 2: 构建图
    print("🕸️  构建图谱...")
    graph = build_graph(contacts, tags)

    # Step 3: 校验
    print("🔬 执行完整性校验...")
    issues = audit_integrity(contacts, tags, graph)

    # Step 4: 找冗余边
    print("🧹 检测冗余边...")
    redundant = find_redundant_edges(graph, tags)

    # Step 5: 输出
    if output_json:
        output = {
            "stats": {
                "contacts": len(contacts),
                "tags": len(tags),
                "issues": len(issues),
                "redundant_edges": len(redundant),
            },
            "graph": graph,
            "issues": issues,
            "redundant_edges": redundant,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        report = generate_report(vault_path, contacts, tags, graph, issues, redundant)
        print(report)

    if issues:
        print(f"\n⚠️  发现 {len(issues)} 个完整性问题，请检查。")
    else:
        print(f"\n✅ 图谱完整性校验通过。")


if __name__ == "__main__":
    main()

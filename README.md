# Relationship Graph Skill

一个 Claude Code skill，帮助你建立和维护个人人脉关系图谱。

将零散的通讯录信息（QQ、微信、名片等）整理为 Obsidian vault 中的结构化条目，用三层原子标签（学校 / 方向 / 城市）做联想触发，让 Claude 在对话中主动推荐"这件事可以问谁"。

## 快速开始

在 Claude Code 中直接说：

- "帮我建一个关系图谱 vault，放在 `~/people/`"
- "记一下这个人：xxx"
- "谁可以帮我搞 xxx？"

Claude 会自动按 skill 流程初始化 vault、录入联系人、维护索引。

## Vault 结构

```
vault-root/
├── README.md              # 设计决策 + 使用约定
├── INDEX.md               # 联系人总览 + 三层标签导航
├── .trash/                # 归档旧文件（不用 rm）
├── contacts/              # 每人一个 .md 文件
├── templates/
│   └── contact.md         # 联系人模板
└── tags/
    ├── school/            # 学校标签
    ├── field/             # 方向/领域标签
    └── city/              # 城市标签
```

## 核心设计

| 设计点 | 说明 |
|--------|------|
| 独立 vault | 联系人含敏感信息，不与博客/工作笔记混放 |
| 原子标签 | 学校、方向、城市三层独立，不搞组合标签 |
| 联系人即桥梁 | 不同圈层的连接通过联系人节点自然形成 |
| 冲突先问 | 疑似重复、信息矛盾时不猜，先问用户 |

## 文档

- `SKILL.md` — 完整 skill 定义（初始化流程、录入、审计、冲突处理、标签管理）
- `assets/onboarding-example.md` — 从零初始化 + 第一个联系人录入的完整示例
- `assets/contact-template.md` — 联系人布局模板（正文 YAML 块 + 四个小节）
- `assets/INDEX-template.md` — INDEX.md 骨架模板
- `scripts/audit_graph.py` — 图谱完整性审计脚本（断链、孤立节点、冗余边）

## TODO

- [ ] 规模边界分析：待积累更多实际数据后，分析标签聚类策略、vault 规模上限、维护成本拐点

# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指引。

## 这是什么

这是一个 **Claude Code skill**（不是软件项目）。它定义了构建个人关系图谱的方法论——
一个人机可读、结构化的知识库，以 Obsidian vault 形式存放。本 skill 告诉 Claude
如何帮用户管理联系人、用三层原子标签体系组织他们，并在对话话题出现时主动推荐可以求助的人。

## 仓库结构

```
relationship-graph/
├── CLAUDE.md              # 本文件——Claude Code 工作指引
├── SKILL.md               # 完整 skill 定义（权威来源）
├── README.md              # 仓库门面（快速开始 + 文档索引）
├── assets/
│   ├── contact-template.md # 联系人布局模板（frontmatter + 正文 YAML 块 + 四个小节）
│   ├── roster-template.md  # 名单布局模板（触发场景 + 成员表格 + 状态规范）
│   ├── INDEX-template.md   # 带空表格的 INDEX.md 骨架
│   └── onboarding-example.md # 从零初始化 + 首个联系人/名单录入的完整示例
└── scripts/
    ├── audit_graph.py      # 图谱审计（INDEX 对账/标签页成员/schema/冲突/日期…）
    └── test_audit_graph.py # 审计回归测试（stdlib unittest，无额外依赖）
```

## 核心概念

**三层原子标签**：学校、方向、城市标签分别存放在 `tags/{school,field,city}/` 三个子目录。
标签是独立的 `.md` 文件，通过 Obsidian wiki-link 连接。绝不创建组合标签
（如"北大数学"）——联系人节点本身就是跨维度的桥梁。

**Vault 隔离**：联系人数据含敏感信息（平台 ID、个人背景），必须存放在独立 vault 目录，
不与公开博客或日常笔记混放。

**触发式召回**：标签即触发器。对话话题命中标签时，Claude 应查 `INDEX.md`，
主动呈现相关联系人。

**名单 vs 联系人**：名单（班级、竞赛队等）记录公共群体成员，一份一个文件在
`rosters/`。成员状态三个值：`已登记`（`[[双链]]` 直达人脉档案）、`仅名单`（只记名字 +
角色，不建文件）、`本人`（名单拥有者自己：纯文本、无双链、不建档、不入计数，
每份至多一行）。名单同样参与触发式召回——命中「触发场景」时浮现整份名单。

## Vault 结构

```
vault-root/
├── README.md              # 使用约定与设计决策
├── INDEX.md               # 速查索引 + 名单导航 + 标签导航（优先读取以做匹配）
├── contacts/              # 每人一个 .md 文件
├── rosters/               # 每份公共名单一个文件（班级、竞赛队……）
├── templates/
│   ├── contact.md         # 从 assets/contact-template.md 复制
│   └── roster.md          # 从 assets/roster-template.md 复制
└── tags/
    ├── school/            # 每个学校一个文件
    ├── field/             # 每个领域一个文件（如 OI 信息竞赛）
    └── city/              # 每个城市一个文件
```

## 联系人文件字段（contacts/*.md）

文件头带 frontmatter（`title` + `type: contact`），结构化数据放在**正文内**的
```yaml 围栏块——两者并存。权威来源是 `assets/contact-template.md`；
写入前先读该 vault 的 `templates/contact.md` 和一个已有联系人文件。
YAML 只含以下键：

| 键 | 类型 | 说明 |
|-----|------|------|
| `nickname` | string | 怎么称呼（主键） |
| `real_name` | string | 法定姓名（可选） |
| `platform` | object | 联系信息唯一事实源：ID 子键（`qq`/`wechat`/`bupt` 类校本键等，可按 vault 本地扩展）+ **昵称子键 `*_nickname`**（QQ/微信显示名——聊天记录认人的 grep 命中点，知道就必须记）+ `other` |
| `identity` | string | 一句话身份（学校/年级/专业/角色） |
| `met` | string | 怎么认识的 |
| `strength` | string | 关系强度：**自由中文词，无枚举、不校验**（参考：密友/熟人/点头之交/刚建联/不熟→预期升温；恩师/队友等类型词可作修饰） |
| `last_contact` | string | 最近有意义互动：`YYYY-MM-DD` 或 `YYYY-MM-DD（注释）`；未知留空，勿写占位词 |

`help_areas`、`trigger_tags`、`notes` 不是 YAML 字段，而是四个正文小节：
`## 可帮事项（AI 联想的核心）`、`## 触发标签`、`## 历史互动`、`## 备注`
（教训写备注，绝不开「备注补充」）。聊天记录的日期块放文件末尾按日期升序。

## 关键设计规则

1. **独立 vault**：联系人文件绝不放进与公开/工作笔记共享的 vault，用专门目录（如 `~/people/`）。
2. **只用原子标签**：学校、方向、城市是三个独立层，联系人节点是桥梁。
3. **真名做文件名**：文件名用真名，别名放进 `nickname` 字段。
4. **图谱卫生**：两个标签若仅因共享联系人相连，删掉这条标签间边——联系人节点是天然桥梁。
5. **安全删除**：重构用 `mv` 到 `.trash/`，绝不用 `rm`。Obsidian 自动忽略 `.trash/`。
6. **批量补全保真**：不覆盖人工评注、不硬截断 identity、删散键必须把信息迁进备注，
   改完必做 `git diff` 抽查 + 审计门禁（详见 SKILL.md「批量补全的保真原则」）。

## 工作流

### 初始化 vault
1. 建目录：`mkdir -p vault-root/{contacts,rosters,templates,tags/{school,field,city}}`
2. 复制 `assets/contact-template.md` → `vault-root/templates/contact.md`
3. 复制 `assets/INDEX-template.md` → `vault-root/INDEX.md`；复制 `assets/roster-template.md` → `vault-root/templates/roster.md`
4. 创建 `README.md`，写明设计决策和使用约定
5. 创建 `.trash/` 目录用于安全归档

### 录入新联系人
1. 逐步收集信息（不要一口气全问；平台 ID 与**显示昵称**都要问）。
2. 按模板布局创建 `contacts/{真名}.md`（frontmatter + 正文 YAML 块 + 四个小节）。
3. 更新 `INDEX.md`——联系人总览表加行（含「缩写·网名」检索列），涉及新标签的在标签导航表加行。
4. 遇到尚不存在的触发标签：先按 SKILL.md 2c 向用户确认，确认后在正确的 `tags/{层}/` 子目录下建文件。
5. 把名字补进每个已存在标签页的成员节（`- [[名]] — 一句话身份`）——漏了就是审计里的
   [标签页] 召回缺口。
6. 确认 `## 触发标签` 小节里所有 `[[wiki-links]]` 都能解析到存在的文件。

### 名单管理
1. 新建：复制 `assets/roster-template.md` → `rosters/{名单名}.md`，填触发场景 + 成员表。
2. 已登记成员姓名列写 `[[档案名]]`；仅名单成员写纯文本名字 + 角色（不建文件）；
   拥有者自己一行状态「本人」（纯文本、无双链、不入计数）。
   姓名、角色固定前两列，之后可加性别/QQ/学号等业务列——状态列审计会自动右起定位。
3. 升级成员：先按「录入新联系人」流程建档，再把名单行改成 `[[名]]` + 状态「已登记」。
4. 同步 `INDEX.md`「名单」导航区，计数写 `N 已登记 / M 仅名单`（含本人加 `（另含本人）`）；
   跑 `scripts/audit_graph.py` 确认无断链、无计数漂移。
   脚本生成的名单：重生成会覆盖正文手工注释，评注放 INDEX/标签页/联系人备注。

### AI 联想匹配
对话话题出现时，搜 `INDEX.md` 匹配触发标签，主动推荐相关联系人。
名单同样参与匹配——命中「触发场景」时浮现整份名单（已登记成员优先，仅名单成员带出）。
匹配过程中绝不创建组合标签。

## 审计清单

`scripts/audit_graph.py`（改它必跑 `test_audit_graph.py`）分级输出：**错误级**
（[断链][孤立][名单][索引][标签页][schema][冲突][格式]）需修复；**提示级**（[提示]）
人工分诊，`--strict` 不因其失败。默认输出紧凑摘要，`--report` 全量，`--json` v2。
pyyaml 缺失时自动降级：结构检查照常、YAML 相关检查显式声明跳过（绝不半盲误报），
`--strict` 在降级模式拒绝运行（退出码 2）。

脚本已自动化的检查：

- 每个联系人里的每个触发标签都指向存在的标签文件；INDEX 里的双链全部可解析。
- INDEX 对账：总览行 ↔ 档案双向完整 + 坏行检测；名单导航 ↔ 文件双向 + **逐份计数核对**；
  标签三层导航 ↔ 文件双向。
- INDEX 单元格漂移：档案 `## 触发标签` 已挂的标签没同步进总览行 → 提示
  （单向核对，档案是事实源；纯文本伪标签格跳过，归专门提示管）。
- **标签页成员双向核对**：人挂了标签页上必须列，页列了人必须挂
  （修复方向属 2c 用户决策；无成员节的 hub 型标签页跳过）。
- 联系人正文 YAML 解析失败（不再静默）、未知/旧顶层键迁移提示、
  昵称滞留注释/other 文案提示、缺 frontmatter、重复备注节。
- 平台 ID 跨档案碰撞（同 QQ 号/学号出现在两人 → 走 2b）。
- last_contact 格式（非法/未来日期 = 错误）与陈旧度（默认 90 天，`--stale-days` 可调；
  只报告，**绝不替用户改日期**）。
- 名单里每个 `[[双链]]` 都指向 `contacts/` 下的档案；状态一致
  （已登记带双链，仅名单/本人不带；本人行每名单至多一行）。
- 仅名单成员已有人脉档案 → 升级为双链（提示）。

仍需人工复核的图规则：学校 ↔ 城市边允许（结构性）；城市 ↔ 城市仅限同区域/相邻；
方向 ↔ 方向仅限同体系（如 OI ↔ ICPC）；删除其他所有跨边——联系人节点是桥梁
（脚本给出冗余边候选）。

## 参考

完整 skill 规范（含设计缘由、联系人布局、INDEX 结构、标签文件模板）见 `SKILL.md`。
`assets/` 下的模板是 vault 初始化时复制的标准形态。

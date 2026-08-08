# Vault 初始化示例

以下是一个完整的 vault 初始化流程 + 第一个联系人录入的示例。
使用虚构人物，展示每一步的最终输出形态。

---

## 步骤 1: 确认 vault 位置

用户说想建一个关系图谱。确认 vault 放在独立目录：

```
D:/people/
```

不放在已有 Obsidian vault 里，因为联系人数据含敏感信息（平台 ID、个人背景）。

## 步骤 2: 创建目录结构

```bash
mkdir -p D:/people/{contacts,templates,tags/{school,field,city}}
```

## 步骤 3: 复制模板

```bash
cp assets/contact-template.md D:/people/templates/contact.md
```

## 步骤 4: 创建 README.md

```markdown
---
title: 人脉库使用说明
type: readme
---

# 人脉库

## 设计决策

- 独立 vault，不与博客/工作笔记混放
- 文件名写真名，别名放字段
- 三层原子标签：学校 / 方向 / 城市，不搞组合标签
- 联系人节点是不同圈层的桥梁

## 使用约定

- 录入前先搜 INDEX.md 防重复
- 创建联系人后同步更新 INDEX
- 不用的文件 mv 到 .trash/，不用 rm
- 定期跑 `python scripts/audit_graph.py <vault_path> --report` 检查完整性
```

## 步骤 5: 创建 INDEX.md

```markdown
---
title: 人脉索引
type: index
---

# 人脉索引

> 速查表：昵称 | 身份 | 触发标签 | 关系强度 | 最近联系
> AI 优先读本文件做联想匹配；详情进对应联系人文件。

## 联系人总览

| 昵称 | 身份 | 触发标签 | 强度 | 最近联系 | 链接 |
| --- | --- | --- | --- | --- | --- |
| | | | | | |

## 按标签检索

### 学校

| 学校 | 触发场景 | 标签文件 |
| --- | --- | --- |
| | | |

### 专业方向

| 方向 | 触发场景 | 标签文件 |
| --- | --- | --- |
| | | |

### 城市

| 城市 | 触发场景 | 标签文件 |
| --- | --- | --- |
| | | |
```

## 步骤 6: 创建 .trash/ 目录

```bash
mkdir -p D:/people/.trash
```

---

## 录入第一个联系人

假设用户说："记一下，陈默，北大的，高中同学，QQ 是 12345，算法很强。"

### 6a. 先搜 INDEX.md 防重复

INDEX 是空的，无重复。

### 6b. 收集信息（逐步追问）

- 全名？→ 陈默
- 怎么称呼？→ 陈默
- 哪个学校？→ 北京大学
- 专业/年级？→ 计算机 2026 级
- 怎么认识的？→ 高中同班
- 关系有多近？→ 高中好友
- 能帮什么？→ 北大校园信息、算法交流
- 触发标签？→ 北京大学、OI 信息竞赛、北京

### 6c. 创建联系人文件

`contacts/陈默.md`：

```markdown
---
title: 陈默
type: contact
---

# 陈默

```yaml
nickname: "陈默"
real_name: "陈默"
platform:
  qq: "12345"
  luogu: ""
  other: ""
identity: "北京大学 计算机 2026 级 · 高中同班"
met: "高中同班同学"
strength: "高中好友"
last_contact: ""
```

## 可帮事项

- 北大校园信息（计算机系）
- 算法交流

## 触发标签

[[北京大学]] [[OI 信息竞赛]] [[北京]]

## 历史互动

- （待补）

## 备注

- （待补）
```

### 6d. 创建 tag 文件（如果不存在）

三个 tag 都不存在，逐个创建：

`tags/school/北京大学.md`：

```markdown
---
title: 北京大学
type: tag
---

# 北京大学

**触发场景**：燕园、保送、8.18 报到、北京

## 相关联系人

- [[陈默]] — 高中同班，计算机 2026 级
```

`tags/field/OI 信息竞赛.md`：

```markdown
---
title: OI 信息竞赛
type: tag
---

# OI 信息竞赛

**触发场景**：NOIP、CSP、NOI、JXOI

## 相关联系人

- [[陈默]] — 高中同班，算法强
```

`tags/city/北京.md`：

```markdown
---
title: 北京
type: tag
---

# 北京

**触发场景**：面基、约饭、大学城

## 相关联系人

- [[陈默]] — 北大
```

### 6e. 更新 INDEX.md

在"联系人总览"表加一行：

```markdown
| 陈默 | 北京大学 计算机 2026 · 高中同班 | [[北京大学]] [[OI 信息竞赛]] [[北京]] | 高中好友 | — | [[陈默]] |
```

在三个 tag 子表各加一行：

```markdown
### 学校

| 北京大学 | 燕园、保送、8.18 报到、北京 | [[北京大学]] |
```

```markdown
### 专业方向

| OI 信息竞赛 | NOIP、CSP、NOI | [[OI 信息竞赛]] |
```

```markdown
### 城市

| 北京 | 面基、约饭、大学城 | [[北京]] |
```

### 6f. 验证 wiki-links

确认 `contacts/陈默.md` 中三个 `[[...]]` 都有对应文件：
- ✅ `tags/school/北京大学.md` 存在
- ✅ `tags/field/OI 信息竞赛.md` 存在
- ✅ `tags/city/北京.md` 存在

---

## 初始化完成后的目录

```
D:/people/
├── README.md
├── INDEX.md
├── .trash/
├── templates/
│   └── contact.md
├── contacts/
│   └── 陈默.md
└── tags/
    ├── school/
    │   └── 北京大学.md
    ├── field/
    │   └── OI 信息竞赛.md
    └── city/
        └── 北京.md
```

后续录入新联系人时，重复步骤 6a–6f：先搜 INDEX → 创建联系人 → 按需创建 tag → 更新 INDEX → 验证 wiki-links。

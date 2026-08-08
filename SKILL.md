---
name: relationship-graph
description: "Build and manage a local personal relationship graph (Personal CRM) as an Obsidian vault. Structurally stores contacts with a three-layer atomic tag system (school/field/city), enabling AI to proactively suggest who can help when a topic comes up in conversation. Triggers: 人脉, 关系图谱, 通讯录, 联系人管理, 认识的人, 找谁帮忙, 人际关系, personal CRM, contact management, relationship network."
agent_created: true
---

# Relationship Graph Builder

## Overview

This Skill provides a complete methodology for building a personal relationship graph —
an AI-readable, structured knowledge base that turns scattered contact information
(QQ, WeChat, business cards, etc.) into searchable, associative entries.
The output is an Obsidian vault with contact files, a three-layer tag system,
and a quick-reference index, supporting both AI-driven matching and graph visualization.

## When to Use

- User wants to systematically manage their contacts (classmates, peers, mentors, partners).
- User has many social-platform contacts (QQ/WeChat/etc.) but lacks structured information.
- User wants AI to proactively surface "who to ask about X" when a topic arises.
- User says things like "remember this person", "create a new contact", "who can help with X".
- User is entering a new environment (university, job, community) and wants to map their network.
- User mentions "building a relationship graph", "personal CRM", or "contact management".

## Design Principles

### Core Problem
Traditional address books store only name + phone number, and AI cannot read them.
Social app contact notes are too short and unstructured.
None of them capture semantic information like "what can this person help with".

### Solution
A standalone Markdown knowledge base (Obsidian vault), one file per person,
using **trigger tags** (`[[标签名]]`) that allow AI to automatically match contacts
when relevant topics appear in conversation.

### Key Design Decisions (from practice)
1. **Independent vault, isolated from daily notes**: Contact data contains sensitive info
   (platform IDs, personal background). Do not mix with public blogs or work notes.
2. **Prioritize semi-familiar, high-potential contacts**: Close friends are already in your head.
   The knowledge base's core value is in "not-that-close but potentially high-value" contacts.
3. **File names use real names**: Aliases/nicknames go in fields, not filenames.
   Pinyin can naturally suggest the real name.
4. **Three-layer atomic tags**: Never create combo tags like "Peking University + Math".
   Instead, school/field/city are three independent layers —
   contact nodes become the bridges between different circles.
5. **Graph hygiene — people are bridges, tags should not over-connect**:
   Delete edges where two tags are linked only through shared contacts.
   The contact nodes should be the network's bridge structure.

## Vault Structure

```
vault-root/
├── README.md              # Usage conventions and design notes
├── INDEX.md               # Quick-reference index + tag navigation (AI reads this first)
├── contacts/              # One .md file per person
├── templates/
│   └── contact.md         # Contact entry template (copy from assets/)
└── tags/
    ├── school/            # School tags (one file per school)
    ├── field/             # Field/domain tags (one file per domain)
    └── city/              # City tags (one file per city)
```

## Data Model

### Contact File Frontmatter

```yaml
---
nickname: ""          # How the person is addressed (primary key; can be alias/nickname)
real_name: ""         # Legal name (optional; leave empty if unknown)
platforms:            # Platform IDs
  qq: ""
  wechat: ""
  bilibili: ""
  luogu: ""           # Competitive programming platforms
  codeforces: ""
  # ...add other platforms as needed
identity: ""          # One-line identity description
context: ""           # How did we meet? Where/when?
strength: ""          # Relationship strength (e.g. best friend / acquaintance / online / not-close→expected-to-grow)
last_contact: ""      # Date of last meaningful interaction (YYYY-MM-DD)
help_areas: []        # What can this person help with? (e.g. ["CMC exam prep", "ICPC team formation"])
trigger_tags: []      # Trigger tags in wiki-link format (e.g. ["[[Peking University]]", "[[OI Competition]]"])
notes: ""             # Remarks, relationship boundaries, dos-and-don'ts
---
```

### Trigger Tag Design
Tags use natural language names (not IDs/codes). Each tag is a standalone `.md` file,
connected via Obsidian wiki-links `[[Tag Name]]`.

**Three-layer classification:**

| Layer | Directory | Content | Edge Rules |
|-------|-----------|---------|------------|
| School | tags/school/ | Specific school names | School ↔ City (bidirectional) |
| Field | tags/field/ | Domains/specialties (e.g. OI Competition, Finance) | Same-system fields may link (e.g. OI ↔ ICPC) |
| City | tags/city/ | City names | Same-region cities may link |

**Forbidden**: Never create "school + field" combo tags (e.g. `Peking University Math`).
The contact node itself should bridge those dimensions.

### Tag File Template

Each tag file in the `tags/` subdirectories should contain:
```markdown
---
title: Tag Name
type: tag
---

# Tag Name

**When this triggers**: Brief description of when this tag is relevant.

## Related Contacts
- [[Contact Name]] — one-line identity
```

### INDEX.md Structure

```markdown
# Contact Index

> Quick-reference table: nickname | identity | trigger tags | strength | last contact
> AI should read this file first for associative matching.
> See individual contact files for full details.

## Contact Overview

| Nickname | Identity | Trigger Tags | Strength | Last Contact | Link |
|----------|----------|-------------|----------|-------------|------|
| ... | ... | [[...]] [[...]] | ... | ... | [[...]] |

## Search by Tag

### Schools
| Tag | When to Trigger | Tag File |
|-----|----------------|----------|
| ... | ... | [[...]] |

### Fields
| Tag | When to Trigger | Tag File |
|-----|----------------|----------|
| ... | ... | [[...]] |

### Cities
| Tag | When to Trigger | Tag File |
|-----|----------------|----------|
| ... | ... | [[...]] |
```

## Workflow

### 1. Initialize the Vault

When the user expresses interest in building a relationship graph:

a) Confirm the vault location. Suggest an independent directory (e.g. `~/people/` or `D:/people/`).
   Explain why isolation matters: contacts contain sensitive info that should not
   mix with public blogs or work notes.

b) Check if the user already has Obsidian vaults (run `ls ~/Documents` or ask).
   If they do, this reinforces the isolation argument.

c) Create the directory structure:
   ```
   mkdir -p vault-root/{contacts,templates,tags/{school,field,city}}
   ```

d) Copy `assets/contact-template.md` to `vault-root/templates/contact.md`.

e) Create initial `README.md` recording the design decisions and usage conventions.

f) Create initial `INDEX.md` with the table structure (empty rows, to be filled).

g) Create the `.trash/` directory for safe archiving of legacy files.
   Use `mv` (not `rm`) to move files there — Obsidian auto-ignores it, and recovery is possible.

### 2. Add a New Contact

a) Collect information from the user (not all at once — ask progressively):
   - How do you address them? (nickname)
   - Which platform? What's their ID? (QQ/WeChat/Bilibili/Luogu/CF...)
   - What's their identity? (school/company/role)
   - How did you meet? How long have you known each other?
   - How close is the relationship?
   - What topics can they help with?
   - Any special notes or boundaries?

b) Create `contacts/{real-name}.md` (if real name unknown, use the commonly used nickname).
   Fill in frontmatter using the template.

c) Update `INDEX.md`:
   - Add a row to the Contact Overview table.
   - Add rows to the tag navigation tables for any new tags.

d) For any trigger tag that doesn't yet exist,
   create the corresponding file in the correct `tags/` subdirectory.

e) After adding, do a quick check: do all `[[wiki-links]]` point to existing files?
   The only exception is template example text (like `[[tag-name]]`).

### 3. AI Associative Matching

During conversation, when a trigger tag keyword appears:
- Look up `INDEX.md` → match tags → list related contacts
- Proactively remind: "On this topic, [Person] might be able to help."
- When the user says "find someone to ask about X", use tags to match contacts.

### 4. Regular Maintenance
- Update `last_contact` after each meaningful interaction.
- Update `help_areas` and `trigger_tags` when discovering new capabilities or role changes.
- Periodically audit the graph: check for broken wiki-links and redundant tag-to-tag edges.

## Graph Hygiene Audit

When performing a full-audit (e.g., after batch imports or tag restructuring):

1. **Contact ↔ Tag**: Every trigger tag in every contact file must point to an
   actually existing tag file. Use a script or manual search to verify.

2. **School ↔ City**: Allowed (structural edge — location relationship).

3. **City ↔ City**: Only same-region or adjacent cities allowed (e.g. Nanjing ↔ Shanghai).

4. **Field ↔ Field**: Only same-system domains allowed (e.g. OI ↔ ICPC, EE ↔ CS).
   Random links like "Medicine ↔ Finance" should be removed.

5. **All other cross-edges**: Should be deleted. If two tags are connected only through
   shared contacts, that edge is useless — the contact node IS the natural bridge.

### Audit Execution

For batch operations (e.g. rewriting all trigger tags across many contact files):

1. Generate a mapping table: contact → current tags → desired new tags.
2. Write a script that iterates contact files and replaces trigger tag blocks.
   Use the Edit tool for small changes, a Python/Bash script for bulk changes.
3. After rewriting, verify all wiki-links resolve:
   ```bash
   # Count all unique wiki-link targets across contact files
   grep -roh '\[\[[^]]*\]\]' contacts/ | sort -u | sed 's/\[\[//;s/\]\]//' | while read tag; do
     # Check if corresponding file exists in tags/ (any layer)
   done
   ```
4. The only expected "broken" links are template example text in `templates/contact.md`.

### Moving Legacy Files
When restructuring (e.g. changing tag naming conventions), do NOT use `rm` for removal.
Instead: `mv old-file.md vault-root/.trash/`. Obsidian auto-ignores `.trash/`.
This avoids OS-level trash issues (especially on Windows where paths with Chinese
characters can break `trash` CLI tools).

## Template Resources

- `assets/contact-template.md` — Frontmatter + body template for new contact entries.
  Copy to `templates/contact.md` during vault initialization.
- `assets/INDEX-template.md` — Full INDEX.md skeleton with empty tables.
  Copy to `INDEX.md` during vault initialization, then fill in as contacts are added.

## Quick Reference

| Action | Steps |
|--------|-------|
| New contact | Collect info → create `contacts/{name}.md` → update INDEX → create tags if needed |
| Who to ask about X? | Search INDEX for trigger tag → list matching contacts |
| After talking to someone | Update `last_contact` in their file |
| Person changed schools/jobs | Update `identity` + `trigger_tags` → update INDEX → add/remove tag files as needed |
| Full audit | Verify all wiki-links → check tag edges → remove redundant cross-edges |

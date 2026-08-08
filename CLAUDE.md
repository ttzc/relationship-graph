# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

This is a **Claude Code skill** (not a software project). It defines a methodology for building a personal relationship graph — an AI-readable, structured knowledge base stored as an Obsidian vault. The skill tells Claude how to help users manage contacts, organize them with a three-layer atomic tag system, and proactively suggest who can help when a topic arises in conversation.

## Repository Layout

```
relationship-graph/
├── CLAUDE.md              # This file — guidance for Claude Code
├── SKILL.md               # Full skill definition (the authoritative source)
└── assets/
    ├── contact-template.md # Frontmatter + body template for new contact entries
    └── INDEX-template.md   # INDEX.md skeleton with empty tables
```

## Core Concepts

**Three-layer atomic tags**: School, Field, and City tags live in separate `tags/{school,field,city}/` subdirectories. Tags are standalone `.md` files connected via Obsidian wiki-links. Never create combo tags (e.g. "Peking University Math") — the contact node itself bridges dimensions.

**Vault isolation**: Contact data contains sensitive info (platform IDs, personal background). It must live in an independent vault directory, never mixed with public blogs or daily notes.

**Trigger-driven recall**: Tags act as triggers. When a conversation topic matches a tag, Claude should look up `INDEX.md` and proactively surface relevant contacts.

## Vault Structure

```
vault-root/
├── README.md              # Usage conventions and design notes
├── INDEX.md               # Quick-reference index + tag navigation (read first for matching)
├── contacts/              # One .md file per person
├── templates/
│   └── contact.md         # Copied from assets/contact-template.md
└── tags/
    ├── school/            # One file per school
    ├── field/             # One file per domain (e.g. OI Competition)
    └── city/              # One file per city
```

## Frontmatter Schema (contacts/*.md)

Every contact file uses YAML frontmatter with these keys:

| Key | Type | Description |
|-----|------|-------------|
| `nickname` | string | How the person is addressed (primary key) |
| `real_name` | string | Legal name (optional) |
| `platforms` | object | Platform IDs: `qq`, `wechat`, `bilibili`, `luogu`, `codeforces`, `other` |
| `identity` | string | One-line identity (school/year/major/role) |
| `context` | string | How/where you met |
| `strength` | string | Relationship strength: close / acquaintance / casual / not-close→expected-to-grow |
| `last_contact` | string | Date of last meaningful interaction (YYYY-MM-DD) |
| `help_areas` | list of strings | What they can help with |
| `trigger_tags` | list of strings | Wiki-link tags that trigger recalling this person |
| `notes` | string | Personality, boundaries, mutual friends |

## Key Design Rules

1. **Independent vault**: Never place contact files inside a vault shared with public or work notes. Use a dedicated directory (e.g. `~/people/`).
2. **Atomic tags only**: School, field, and city are three independent layers. The contact node is the bridge.
3. **Real names for filenames**: File names use real names. Aliases go in the `nickname` field.
4. **Graph hygiene**: When two tags are connected only through shared contacts, delete that tag-to-tag edge — the contact node is the natural bridge.
5. **Safe deletion**: Use `mv` to `.trash/` for restructuring, never `rm`. Obsidian auto-ignores `.trash/`.

## Workflows

### Initialize a Vault
1. Create directory: `mkdir -p vault-root/{contacts,templates,tags/{school,field,city}}`
2. Copy `assets/contact-template.md` → `vault-root/templates/contact.md`
3. Copy `assets/INDEX-template.md` → `vault-root/INDEX.md`
4. Create `README.md` with design decisions and usage conventions
5. Create `.trash/` directory for safe archiving

### Add a New Contact
1. Collect info progressively (don't ask for everything at once).
2. Create `contacts/{real-name}.md` with frontmatter from the template.
3. Update `INDEX.md` — add row to Contact Overview table, and tag navigation tables for any new tags.
4. Create tag files in the correct `tags/{layer}/` subdirectory for any new tags.
5. Verify all `[[wiki-links]]` in trigger_tags resolve to existing files.

### AI Associative Matching
When a conversation topic appears, search `INDEX.md` for matching trigger tags and proactively suggest relevant contacts. Never create combo tags during matching.

## Audit Checklist

- Every `trigger_tag` in every contact file points to an existing tag file.
- School ↔ City edges are allowed (structural).
- City ↔ City edges only for same-region/adjacent cities.
- Field ↔ Field edges only for same-system domains (e.g. OI ↔ ICPC).
- Delete all other cross-edges — contact nodes are the bridges.

## Reference

The full skill specification (including rationale, frontmatter examples, INDEX structure, and tag file template) is in `SKILL.md`. The templates in `assets/` are the canonical forms to copy during vault initialization.

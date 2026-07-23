# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository purpose

This repo is a Claude Code **marketplace** that hosts multiple plugins. Each plugin is a self-contained collection of skills and/or commands distributed together. There is no build, lint, or test step: skills and commands are plain markdown files (plus the occasional helper script) that Claude Code loads at runtime.

Consumers install it with `/plugin marketplace add TadejSlivnik/claude-skills`, then enable individual plugins.

## Layout

- `.claude-plugin/marketplace.json` — the marketplace manifest at the repo root (marketplace `name` is `ts-skills`). It lists every plugin in the `plugins[]` array. Each entry's `source` is a relative path to the plugin's directory, e.g. `"./plugins/planning"` (bare `"."` fails schema validation). An entry may set `"defaultEnabled": false` to ship a plugin that stays off until the user opts in.
- `plugins/<plugin-name>/` — one directory per plugin. Each contains:
  - `.claude-plugin/plugin.json` — that plugin's manifest (`name` matching the directory, `description`, `author`, `homepage`, `repository`, `license`).
  - `skills/<skill-name>/SKILL.md` — one directory per skill. Each `SKILL.md` is YAML-frontmatter (`name`, `description`) markdown. The `description` is the trigger contract — Claude Code uses it to decide when to invoke the skill, so it must state *what the skill does* and *when to use it* (typically ending in "Use when...").
  - `commands/<command-name>.md` — optional slash-command definitions, each YAML-frontmatter markdown with a `description`.

Current plugins:
- `planning` — stress-testing plans/designs through structured questioning (`grill-me`, `handoff`).
- `git-tools` — git workflow slash commands (`/cm` generates a Conventional Commits message; `/commit` generates one and commits).
- `clickup` — read/write ClickUp tasks and docs; the skill ships a Python helper at `skills/clickup/scripts/clickup.py`.
- `code` — writing/reviewing/hardening code (review, simplification, security, performance, TDD, debugging, frontend, planning, interview).
- `experimental` — in-development skills under evaluation; `defaultEnabled: false`. Skills graduate out of here once verified.

## Progressive disclosure

Keep `SKILL.md` bodies tight. When a skill needs long checklists or deep reference material, put it in a `references/` subdirectory beside the `SKILL.md` (see `plugins/code/skills/*/references/`) and point to it from the body, rather than inlining everything. Bundled helper scripts live under a `scripts/` subdirectory (see the clickup skill).

## Skills should be self-contained

Prefer self-contained skills/commands: it's good when a skill or command does NOT depend on or cross-reference another — no "see the other-skill" / `Related:` pointers to siblings. Each skill is loaded independently based on its own trigger description, so a cross-skill reference can dangle and rot as skills move or get reworded. Writing needed guidance inline (even if it duplicates content elsewhere) buys independence.

This is a preference, not a hard rule. Where a genuine single-source-of-truth is worth more than independence, sharing is fine — e.g. `/commit` inlines the commit-message rules that `/cm` also uses (so it works standalone, since `/cm` is instructed not to commit); duplication there is deliberate. (A `Related:` pointer to a section *within the same skill* is always fine.)

## Adding a plugin

1. Create `plugins/<kebab-name>/.claude-plugin/plugin.json` with at least `name` (matching the directory) and `description`.
2. Add `skills/` and/or `commands/` directories under the plugin as needed.
3. Register the plugin in `.claude-plugin/marketplace.json` by appending an entry to `plugins[]` with `name`, `source` (`"./plugins/<kebab-name>"`), and `description`.

## Adding a skill (to an existing plugin)

1. Create `plugins/<plugin-name>/skills/<kebab-name>/SKILL.md`.
2. Frontmatter: `name` (matches directory) and `description` (one or two sentences ending in a "Use when..." trigger phrase).
3. Body: imperative instructions to Claude. Keep it tight; prefer `references/` bundles over long monolithic prompts.

## Releasing

Installation is git-based — pushing to `main` on GitHub is the release; no manifest carries a `version` field today and the schema does not require one. If you introduce versioning, add `version` to the relevant `plugin.json` (not `marketplace.json`) and bump it on user-visible changes to that plugin's skills or metadata.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository purpose

This repo is a Claude Code **marketplace** that hosts multiple plugins. Each plugin is a self-contained collection of skills and/or commands distributed together. There is no build, lint, or test step: skills and commands are plain markdown files that Claude Code loads at runtime.

## Layout

- `.claude-plugin/marketplace.json` — the marketplace manifest at the repo root. It lists every plugin in the `plugins[]` array. This is what gets added via `/plugin marketplace add TadejSlivnik/claude-skills`. Each entry's `source` field is a relative path to the plugin's directory, e.g. `"./plugins/planning"` (a relative path; bare `"."` fails schema validation).

Current plugins: `planning` (design/plan stress-testing skills) and `git-tools` (git workflow commands).
- `plugins/<plugin-name>/` — one directory per plugin. Each contains:
  - `.claude-plugin/plugin.json` — that plugin's manifest (`name`, `description`, `author`, etc.).
  - `skills/<skill-name>/SKILL.md` — one directory per skill. Each `SKILL.md` is a YAML-frontmatter (`name`, `description`) markdown file. The `description` is the trigger contract — Claude Code uses it to decide when to invoke the skill, so it must clearly state *what the skill does* and *when to use it*.
  - `commands/<command-name>.md` — optional slash-command definitions, each a YAML-frontmatter markdown file with a `description`.

## Adding a plugin

1. Create `plugins/<kebab-name>/.claude-plugin/plugin.json` with at least `name` (matching the directory) and `description`.
2. Add a `skills/` and/or `commands/` directory under the plugin as needed.
3. Register the plugin in `.claude-plugin/marketplace.json` by appending an entry to `plugins[]` with `name`, `source` (`"./plugins/<kebab-name>"`), and `description`.

## Adding a skill (to an existing plugin)

1. Create `plugins/<plugin-name>/skills/<kebab-name>/SKILL.md`.
2. Frontmatter: `name` (matches directory) and `description` (one or two sentences ending in a "Use when..." trigger phrase).
3. Body: instructions to Claude written in the imperative. Keep it tight — progressive disclosure via bundled resources is preferred over long monolithic prompts.

## Releasing

Installation is git-based — pushing to `main` on GitHub is the release; no manifest carries a `version` field today and the schema does not require one. If you introduce versioning, add `version` to the relevant `plugin.json` (not `marketplace.json`) and bump it on user-visible changes to that plugin's skills or metadata.

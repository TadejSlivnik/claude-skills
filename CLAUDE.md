# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository purpose

This repo is the `ts-skills` Claude Code **plugin** — a collection of skills distributed via a Claude Code marketplace. There is no build, lint, or test step: skills are plain markdown files that Claude Code loads at runtime.

## Layout

- `.claude-plugin/plugin.json` — plugin manifest consumed when this repo is installed as a plugin.
- `.claude-plugin/marketplace.json` — marketplace manifest so this repo can be added via `/plugin marketplace add TadejSlivnik/claude-skills`. The `plugins[].source` field must be `"./."` (a relative path; bare `"."` fails schema validation).
- `skills/<skill-name>/SKILL.md` — one directory per skill. Each `SKILL.md` is a YAML-frontmatter (`name`, `description`) markdown file. The `description` is the trigger contract — Claude Code uses it to decide when to invoke the skill, so it must clearly state *what the skill does* and *when to use it*.

## Adding a skill

1. Create `skills/<kebab-name>/SKILL.md`.
2. Frontmatter: `name` (matches directory) and `description` (one or two sentences ending in a "Use when..." trigger phrase).
3. Body: instructions to Claude written in the imperative. Keep it tight — progressive disclosure via bundled resources is preferred over long monolithic prompts.

## Releasing

Installation is git-based — pushing to `main` on GitHub is the release. Bump `version` in `marketplace.json` when making user-visible changes to plugin metadata or skill behavior.

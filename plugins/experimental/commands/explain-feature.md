---
description: High-level, documentation-worthy summary of how a feature behaves, written for non-programmers
argument-hint: <endpoint, feature, module, or files — omit to summarize what we worked on in this conversation>
---

Write a high-level summary of how the logic works for: $ARGUMENTS

If no argument was given, summarize the feature that was built or discussed most recently in this conversation. If the scope is genuinely ambiguous, ask one short question before writing.

First, make sure you actually understand the behavior: read the relevant code end to end if you haven't already in this conversation. Summarize what the code *does today*, not what was planned.

## Audience and purpose

The reader is a non-programmer (product, marketing, an external partner) who needs to understand what the feature does and how it behaves — documentation material, suitable for pasting into a project tracker like ClickUp. It must be accurate enough that a developer would also sign off on it.

## What to include

- **What it is / what it returns** — lead with the purpose and the user-visible output, in one or two sentences.
- **The behavior, step by step** — how inputs change the result: filters, ordering, fallbacks, defaults, limits, rotation/randomness, caching. Describe *behavior*, not implementation ("the selection rotates daily" — not "a blake2b hash seeds a Fisher-Yates shuffle").
- **Deliberate design decisions visible to the outside** — e.g. "spot types with no relevant products return an empty list so the widget can hide itself", default exclusions, fallback rules.
- **Parameter names** (`sort`, `firm_id`, …) are fine to mention since integrators read this too — but explain each in plain words.

## What to leave out

- Tests, test coverage, or how anything was verified
- Dev tooling: Bruno/Postman requests, lint, migrations, CI
- File paths, function/class names, code identifiers (except public API parameter names)
- Internal constants and code-level reasoning (cap sizes, index choices, query strategies) — unless the *behavior* they cause matters to the reader, in which case state the behavior only
- Performance war stories, nitpicks, edge-case caveats that don't change how a normal consumer experiences the feature
- Editorializing about the code ("deliberately", "cleverly", "note that…") — just state what happens

## Format

- Start with the feature name and, for endpoints, the method + path
- Short labeled sections or bolded lead-ins (e.g. **Filters**, **Ordering**, **Caching**) — prose under each, bullets only for true enumerations
- No "one sentence TL;DR" footer, no meta commentary about the summary itself
- Markdown that renders well in project trackers (ClickUp, Linear, Jira)

After writing the summary, output it directly in the conversation. Don't post it anywhere unless asked.

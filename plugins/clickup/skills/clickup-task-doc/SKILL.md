---
name: clickup
description: Read or write ClickUp tasks and docs by ID or URL. Use when the user invokes /clickup, pastes a ClickUp task or doc URL, or says "get clickup task/doc X", "work on clickup task X", "create a clickup task", "update/close/reassign a task", "set status/priority/tags on a task", "file a ticket in <list>", "write this up as a clickup doc".
---

# ClickUp

Five operations: `task get`, `task create`, `task update`, `doc get`, `doc create`.
Reads are safe; **writes proceed directly when the user asks — no confirmation prompt.**

## Setup (one-time, shared across task + doc)

Tokens live in `~/.config/clickup/profiles.json` (override with `$CLICKUP_PROFILES`).
This file is outside the skill dir on purpose — the skill dir syncs to git.

```jsonc
{
  "profiles": {
    "work": {
      "token": "pk_...",
      "team_id": "9000...",
      "lists":       { "backlog": "901100..." },                   // optional, for task create
      "doc_parents": { "specs":   { "id": "90110...", "type": 4 } } // optional, for doc create
    },
    "personal": { "token": "pk_...", "team_id": "9001..." }
  }
}
```

- Token: ClickUp → avatar → Settings → Apps → API Token → Generate. One per account.
- `team_id` = workspace id (number after `/t/` or after the host in a URL). Required
  for custom task IDs (`DEV-123`) and for all Doc operations.
- `doc_parents` types: 4=Space, 5=Folder, 6=List, 12=Doc. Omit `--parent` to create
  at workspace root.
- `python3 scripts/clickup.py profiles` lists configured profiles.
- Fallback when no config file exists: `CLICKUP_API_TOKEN` (+ optional `CLICKUP_TEAM_ID`).

### Creating the config when it's missing

If `~/.config/clickup/profiles.json` doesn't exist (and no `CLICKUP_API_TOKEN`
fallback is set), **don't fail — offer to create it.** Ask the user for the
required fields, then write the file:

- **token** (required) — see the API Token instructions above.
- **team_id** (required for custom task IDs and all Doc ops) — workspace id.
- **profile name** — default to `work` if they only have one.
- **lists** / **doc_parents** — optional; ask only if they want to set up
  `task create` / `doc create` now (they can add these later).

Write with `0600` permissions and confirm the path back to the user. Never echo
the token in your confirmation.

### When the user supplies list or doc_parent ids

Whenever the user gives a `lists` entry or a `doc_parents` entry (now or later),
**ask what that list/parent is used for** and record it as a short comment on
the JSON entry. This context lets you route future `task create` / `doc create`
calls to the right place without asking again. For example:

```jsonc
"lists": {
  "backlog": "901100...",  // unscheduled feature work, triaged weekly
  "bugs":    "901101..."   // production defects, ops triages daily
}
```

## Profile resolution (applies to every command)

Explicit `--profile` (or trailing arg on `get`) wins → else auto-match the workspace
id parsed from a pasted URL → else the single configured profile. If multiple
profiles exist and none match, **ask the user which project** before retrying.
Never invent a profile.

## Reads — `task get`, `doc get`

Run from the skill directory:

```bash
python3 scripts/clickup.py task get "<task-id-or-url>" [profile]
python3 scripts/clickup.py doc  get "<doc-id-or-url>"  [profile]
```

The script prints JSON.

- **Tasks**: `description` + `comments[]`. **Always read comments** — clarifications
  and scope changes live there; the latest comment overrides the description on
  conflicts.
- **Docs**: `pages[]` in document order. Read all pages; specs are often split.

After fetching, restate the work as a 2–4 bullet brief (what to build, acceptance
criteria, anything ambiguous), then hand off to the actual implementation per the
project's CLAUDE.md. If the user only wanted to *see* it, stop at the brief.

## Writes — `task create`, `doc create`

Compose title + markdown body in `clickup-format` style: self-contained, no
conversational filler, tables for structured decisions, `- [ ]` for acceptance
criteria. Write the body to a temp file (`/tmp/clickup_*.md`), then run the
create directly (no `--dry-run`, no confirmation prompt):

**Assignees default to "me"** (the token owner): a new task with no `--assignees`
flag is auto-assigned to the token's user. Pass `--assignees none` to leave it
unassigned, `--assignees me` to be explicit, or a comma list of numeric ids
(the literal `me` may appear in the list and resolves to the token owner). Only
pass `--assignees` when the user names a different assignee or asks for none.

```bash
python3 scripts/clickup.py task create --list <alias|id|url> --name "<title>" \
  --content-file /tmp/clickup_task.md [--profile p] [--priority N] [--status S] \
  [--tags a,b] [--assignees me|id,...|none]

python3 scripts/clickup.py doc create --name "<title>" \
  --content-file /tmp/clickup_doc.md [--profile p] [--parent <alias>]
```

Report the returned URL. Docs are created `PRIVATE`; sharing happens in ClickUp.

## Writes — `task update`

Change an existing task in place. Pass the task id/url, then only the flags for
the fields you're changing — unspecified fields are left untouched. Proceeds
directly when the user asks (no confirmation prompt).

```bash
python3 scripts/clickup.py task update <id|url> [profile] \
  [--status "<name>"] [--priority N|none] [--name "<title>"] \
  [--content-file /tmp/clickup_desc.md] [--description "<text>"] \
  [--due <ms>|none] [--archived true|false] \
  [--add-assignees id,..] [--rem-assignees id,..] \
  [--add-tags a,b] [--rem-tags a,b] [--dry-run]
```

- **Status** names are **list-specific**, not global. There is no universal
  "done"/"complete" — fetch the task first (`task get`) or inspect the list's
  statuses and use the exact string (e.g. `to do`, `code review`,
  `ready to deploy`, `shipped`). If a guessed status fails with "Status does not
  exist", look up the real ones and retry; if several plausibly mean "done",
  ask the user which.
- **Priority**: `1`=urgent, `2`=high, `3`=normal, `4`=low; `none` clears it.
- **Assignees** are add/remove by **numeric user id** (not username) — get ids
  from a `task get` if needed. Same for due date (`none` clears).
- **Tags** are added/removed one at a time via dedicated endpoints; a PUT does
  **not** replace the whole tag set, so use `--add-tags`/`--rem-tags`.
- Custom task ids (`DEV-123`) need the profile's `team_id` (handled automatically).
- Use `--dry-run` to preview the exact PUT/POST/DELETE calls before sending.

The script prints the task's resulting status, priority, assignees, and tags.

`--dry-run` still exists on both commands — use it only if *you* need to verify
the resolved endpoint/body before posting, not to gate on the user. Once the
user has asked for the task/doc, just create it.

## Rules

- Never print or log the token.
- When the user asks to create or update a task/doc, do it directly — don't ask for confirmation first.
- When in doubt about which profile, list, or parent to use, **ask**.
- `clickup-format` produces text the user pastes by hand; `clickup create` pushes
  via the API. Use create when the user wants it filed; format when they want to
  paste it themselves.

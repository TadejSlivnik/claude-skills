---
name: multica
description: Read and drive a Multica cloud workspace — get issues and comments, dispatch work to agents, push agent instructions, cancel duplicate runs, and diagnose a stalled pipeline. Use when the user invokes /multica, pastes a multica.ai issue URL, names an issue key like WEBS-41, or says "check that task", "why did this stall", "hand it to the Reviewer", "update the agent instructions", "is the runtime up".
---

# Multica

A Multica workspace runs **agents** against **issues**. Work moves by *dispatching* an
issue to an agent, which starts a run on a **runtime** (a machine running the Multica
daemon). Everything below is about doing that without firing duplicate runs or stalling
the pipeline silently.

Run commands from the skill directory: `python3 scripts/multica.py ...`

## Setup (one-time)

Config lives in `~/.config/multica/profiles.json` (override with `$MULTICA_PROFILES`).
Outside the skill dir on purpose — the skill dir syncs to git.

```jsonc
{
  "profiles": {
    "websites": {
      "token": "mul_...",                          // personal access token
      "workspace_id": "5fd55892-4180-43f5-9b34-751d16442313",
      "agents_dir": "~/www/privat/multica/agents"  // optional, for `agents push`
    }
  }
}
```

- **token**: Multica → Settings → personal access token. `mul_` prefix. It has no
  scoping — it is the whole account.
- **workspace_id**: the UUID sent as `X-Workspace-ID`. Most endpoints need it.
- **agents_dir**: where `_conventions.md` and `<agent>.md` live. Only `agents push`
  uses it.
- Fallback when no config exists: `MULTICA_TOKEN` (+ `MULTICA_WORKSPACE_ID`).
- `python3 scripts/multica.py profiles` lists what is configured.

**Agent ids are never stored in config** — they are resolved by name on every call, so
adding or renaming an agent needs no config edit.

### Creating the config when it's missing

Don't fail — offer to create it. Ask for token and workspace id (and `agents_dir` if
they maintain agent instructions as files), write with `0600`, confirm the path back.
**Never echo the token.**

## The dispatch model — read this before assigning anything

**Nothing fires when an issue changes status.** There are exactly four triggers:

1. **Assigning an issue to an agent** — but only when the assignee *actually changes*,
   and never from `backlog`.
2. **Mentioning it** as `[@Name](mention://agent/<uuid>)`. A bare `@Name` is plain text
   and wakes nobody.
3. **A comment by anyone else on an issue already assigned to that agent.** No mention
   needed. This one is undocumented and is the easiest way to double-dispatch.
4. Direct chat, and autopilots (schedule or webhook only).

So the safe handoff is: **say everything first, then assign, then stop.** Never assign
and then add a follow-up comment — that comment is a second, independent run doing the
same work in parallel.

`issue dispatch` does this in the right order and refuses the two silent failures:

```bash
python3 scripts/multica.py issue dispatch WEBS-41 --to Planner --comment-file /tmp/note.md
```

- Already assigned to that agent → **refuses**, because re-assigning is a no-op that
  fires nothing and stalls the work invisibly. Post a comment instead — for an agent
  that already holds the issue, the comment *is* the trigger.
- Issue in `backlog` → **refuses**, because assignment never triggers from there.
- Posts the comment before assigning, then re-reads to confirm the assignee changed.

`--force` overrides either guard; `--dry-run` prints the plan.

## Reading

```bash
python3 scripts/multica.py issue get WEBS-41 [--comments 10] [--json]
```

Accepts an issue key, a multica.ai URL, or a raw UUID. Prints the issue plus its most
recent comments.

**Always read the comments.** Scope changes, gate decisions and the `## Pipeline`
routing plan all live there, and the latest comment overrides the description on
conflicts. A comment whose `author_type` is `system` is the platform's own
stage-completion notification.

## Commenting

```bash
python3 scripts/multica.py issue comment WEBS-41 --file /tmp/note.md
python3 scripts/multica.py issue comment WEBS-41 --text "one-liner"
```

Warns on stderr when the issue is assigned to an agent, because the comment dispatches
a run. That is usually what you want when waking a stuck agent — just know it happens.

## Creating

```bash
python3 scripts/multica.py issue create --title "..." --project mydash \
  [--parent WEBS-11] [--stage 3] [--description-file /tmp/body.md] [--assign Planner]
```

New issues land in **`todo`**, not `backlog` — verified against a live workspace, and
worth knowing because assignment never triggers from `backlog`. `--assign` checks the
category and only forces `todo` when it has to, then assigns. `--project` takes a name
or a UUID.

## Pushing agent instructions

```bash
python3 scripts/multica.py agents push              # every agent file in agents_dir
python3 scripts/multica.py agents push reviewer auditor
```

Each agent's Instructions = `_conventions.md` + `\n\n---\n\n` + `<agent>.md`, uploaded
via `PUT /agents/{id}`, then **read back and compared** — this API returns 200 for
fields it silently drops, so a 200 alone proves nothing.

An agent file whose first line is `<!-- standalone -->` is uploaded **without** the
conventions prepended. That is how agents outside the squad (diagnostics, one-off
helpers) opt out.

## Diagnosing a stall

```bash
python3 scripts/multica.py status            # runtime online? which CLI? failures in 24h
python3 scripts/multica.py runs --failed
python3 scripts/multica.py runs --agent Planner --limit 5
python3 scripts/multica.py runs cancel <task-id>
```

Start with `status`. Failures that look like the pipeline's fault usually are not:

- **`401 OAuth access token has been revoked`** — the *provider* login on the runtime
  host expired, not Multica auth. `multica auth status` will still look healthy. Fix by
  re-authenticating the coding CLI on that host.
- **`400 ... does not support this model; version X or newer is required`** — one
  agent's model is newer than the runtime's CLI. Check per-agent `model`; only the
  agents using that model fail. After upgrading the CLI, **restart the daemon** — it
  detects the version once at startup and reports the stale one until it restarts.
- **Two runs doing the same work** — something assigned *and* mentioned, or commented
  after assigning. Cancel the duplicate; keep the one on the right issue.

## API facts that cost real time

The API has no OpenAPI spec and the published docs are wrong or silent on several
points. These were established by probing a live workspace:

- The parent field on a sub-issue is **`parent_issue_id`** when reading, but
  **`parent_id`** in the create body. Reading `parent_id` returns nothing and makes
  correctly-parented sub-issues look orphaned.
- A comment's body field is **`content`** — `body` and `text` both fail.
- **Agents want `PUT`** (`PATCH` returns 405). **Autopilots want `PATCH`** (`PUT`
  returns 405).
- **Skills attach only via `PUT /agents/{id}/skills`.** `skill_ids` in the agent body is
  accepted and silently ignored; `POST .../skills` is 405.
- **`DELETE` on an agent is 405** — archive via `POST /agents/{id}/archive`. There is no
  un-archive, so archiving is one-way.
- **Accepted ≠ stored.** `runbook` on an autopilot, `skill_ids` on an agent, `member_ids`
  on a squad and autopilot subscribers all return 2xx and store nothing. Read back
  anything that matters.
- Squad members use **`member_id`**, not `agent_id`.
- Issue statuses are custom but pinned to seven fixed categories
  (`backlog todo in_progress in_review blocked done cancelled`). They are labels on a
  board, not triggers — a status in the `blocked` category is how a human gate is
  modelled. An issue carries **three** fields: `status`, `status_category` and
  `status_name`. Branch on **`status_category`** — it is the one of the seven, and it
  survives the user renaming a custom status.
- **Sub-issue stages** drive the platform's own loop: when every sub-issue in the
  earliest unfinished stage reaches `done`, Multica posts a system comment mentioning
  the *parent's assignee*, which wakes it. Stage is settable at creation and updatable
  later (`PUT /issues/{id} {"stage": N}`), and several sub-issues may share a stage.
  Completions get **batched** — reconcile real state on waking rather than trusting the
  notification.
- Runs are reachable only per agent (`GET /agents/{id}/tasks`). There is no `/tasks` or
  `/runs` collection.

## Rules

- **Never print or log the token**, and never echo a composed DSN or URL containing it.
- Never guess a profile, project or agent name. If several could match, **ask**.
- Reads are safe. Writes proceed directly when the user asks — no confirmation prompt —
  but a *dispatch* starts real work on a real machine, so get the target right.
- After any write, prefer reading back over trusting the status code.

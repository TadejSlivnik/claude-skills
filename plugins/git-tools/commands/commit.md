---
description: Generate a commit message (via /cm) and commit — staged changes if any, otherwise all tracked and untracked changes
model: haiku
---

Generate the commit message by invoking the `git-tools:cm` skill (via the Skill tool). Reuse its output as-is — do **not** restate or duplicate its message-writing rules here; cm is the single source of truth for how the message is written. Strip the surrounding code fence; the message may be multi-line (subject + body).

**Note:** `cm` will end with "do NOT run git commit / only print the message." That instruction applies to `cm` when run standalone. Here it is a **sub-step** — after it returns the message, do not stop; you **must** proceed to stage and commit as described below.

Then commit, matching the same scope `/cm` inspected:

1. Run `git status --short` to see what is staged vs. unstaged vs. untracked.
2. If there are **staged** changes, commit only those.
3. If **nothing is staged**, stage everything (tracked modifications and untracked files) with `git add -A`, then commit.

Pass the message to `git commit` with one `-m` per blank-line-separated block — e.g. `git commit -m "<subject>"` for a subject-only message, `git commit -m "<subject>" -m "<body>"` when cm returned a body, and an extra `-m "<footer>"` when it also returned a footer (breaking-change / issue trailers).

Rules:
- Use the message exactly as `/cm` produced it.
- Before staging untracked files, glance at `git status --short` — if any newly staged file looks like it could hold secrets (`.env`, keys, credentials, tokens), read its contents first and flag it rather than committing blindly.
- Never `git push`.
- If the working tree is completely clean (nothing staged, modified, or untracked), say so and do not commit.
- After committing, run `git log -1 --oneline` and show it so the user can confirm the result.

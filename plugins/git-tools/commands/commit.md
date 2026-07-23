---
description: Generate a commit message and commit — staged changes if any, otherwise all tracked and untracked changes
model: haiku
---

Run `git diff --cached` to see staged changes. If nothing is staged, also run `git diff` to see unstaged changes and `git status --short` to see untracked files (read the contents of any new file with `git diff --no-index /dev/null <file>` so the message reflects them too).

Then write the commit message in this shape:

```
<type>(<optional scope>): <subject>

<optional body>

<optional footer(s)>
```

Guidelines:

**Subject line** (always):
- **Type:** the one that fits the dominant change — `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `build`, `ci`, `ops`, `chore`, `style`, `revert`
- **Scope:** optional short area name (module/app touched); match the scope convention already visible in the repo's `git log`
- Imperative mood ("add", "fix", "update" — not "added"/"adds")
- Capitalize the first letter of the subject; no trailing period
- Keep the whole line (type + scope + subject) under ~50 characters
- Describe the *why* or the user-visible change, not a file list

**Body** (only when the subject cannot stand alone):
- Separate it from the subject with one blank line
- Wrap lines at ~72 characters
- Explain *what* changed and *why* — not *how* (the diff shows how)
- Omit the body entirely for small, self-explanatory changes — do not pad a trivial change with a body

**Footer** (only when applicable):
- Separate it from the body (or subject, if no body) with one blank line
- Use it for machine-readable trailers: breaking changes and issue references
- `BREAKING CHANGE: <description>` for any incompatible change (or mark the type with a `!`, e.g. `feat!:`)
- Reference issues the commit closes or relates to — `Closes #123`, `Refs #456`
- Only add a footer when there is something concrete to record; never invent an issue number

If changes span multiple unrelated areas, pick the dominant one for the subject and use the body to note the others, so the user can consider splitting the commit.

Then commit, matching the same scope you inspected:

1. Run `git status --short` to see what is staged vs. unstaged vs. untracked.
2. If there are **staged** changes, commit only those.
3. If **nothing is staged**, stage everything (tracked modifications and untracked files) with `git add -A`, then commit.

Pass the message to `git commit` with one `-m` per blank-line-separated block — e.g. `git commit -m "<subject>"` for a subject-only message, `git commit -m "<subject>" -m "<body>"` when there's a body, and an extra `-m "<footer>"` when there's also a footer (breaking-change / issue trailers).

Rules:
- Before staging untracked files, glance at `git status --short` — if any newly staged file looks like it could hold secrets (`.env`, keys, credentials, tokens), read its contents first and flag it rather than committing blindly.
- Never `git push`.
- If the working tree is completely clean (nothing staged, modified, or untracked), say so and do not commit.
- After committing, run `git log -1 --oneline` and show it so the user can confirm the result.

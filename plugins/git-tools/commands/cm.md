---
description: Generate a best-practice Conventional Commits message from the current changes
model: haiku
---

Run `git diff --cached` to see staged changes. If nothing is staged, also run `git diff` to see unstaged changes and `git status --short` to see untracked files (read the contents of any new file with `git diff --no-index /dev/null <file>` so the message reflects them too).

Then output **only** the commit message inside a single fenced code block (so it's easy to copy) — no explanation, no surrounding text, no trailing summary:

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

Do NOT run `git commit`. Do NOT stage files. Only read the diff and print the message.

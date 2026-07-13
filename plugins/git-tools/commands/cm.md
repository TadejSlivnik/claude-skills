---
description: Generate a one-line short commit message from staged changes
model: haiku
---

Run `git diff --cached` to see staged changes. If nothing is staged, also run `git diff` to see unstaged changes.

Then output **only** a single short commit message line inside a fenced code block (so it's easy to copy) — no explanation, no surrounding text, no trailing summary. Just the message itself on one line, wrapped in a code block like:

```
your commit message here
```

Guidelines for the message:
- Imperative mood ("add", "fix", "update" — not "added"/"adds")
- Lowercase first letter unless it's a proper noun
- No trailing period
- Aim for under 60 characters
- Focus on the *why* or the user-visible change, not a file list
- If changes span multiple unrelated areas, pick the dominant one and prefix the message with a note like `(mixed) ` so the user knows to consider splitting the commit

Do NOT run `git commit`. Do NOT stage files. Only read the diff and print the message.

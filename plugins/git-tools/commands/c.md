---
description: Generate a commit message (via /cm) and commit — staged changes if any, otherwise all tracked unstaged changes
---

Generate the commit message by invoking the `git-tools:cm` skill (via the Skill tool). Reuse it as-is — do **not** restate or duplicate its message-writing rules here. Take the single-line message it returns and strip the surrounding code fence.

Then commit, matching the same scope `/cm` inspected:

1. Run `git status --short` to see what is staged vs. unstaged.
2. If there are **staged** changes, commit only those: `git commit -m "<message>"`.
3. If **nothing is staged**, commit all tracked modifications: `git commit -a -m "<message>"`.

Rules:
- Use the message exactly as `/cm` produced it.
- Never `git add` untracked files and never `git push`.
- If the working tree is completely clean (nothing staged, nothing modified), say so and do not commit.
- After committing, run `git log -1 --oneline` and show it so the user can confirm the result.

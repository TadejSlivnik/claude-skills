---
description: Squash all commits on the current branch into one, keeping every change — via a soft reset to the branch's fork point
---

Collapse every commit the current branch has added on top of its base branch into a single commit, preserving all file changes exactly. Use a soft reset to the fork point so this works even if the base branch has moved on.

## 1. Safety checks

1. Run `git status --short`. If the working tree is **dirty** (staged, modified, or untracked changes), stop and tell the user — squashing should start from a clean tree so the single commit contains only the branch's committed work. Let them commit or stash first.
2. Run `git rev-parse --abbrev-ref HEAD` to get the current branch. If it is `main` or `master`, stop — there is nothing to squash onto.

## 2. Determine the base branch and fork point

- The base branch is whichever of `master` or `main` exists (`git rev-parse --verify master` / `main`). If both exist, prefer the one the branch actually diverged from (the one with the nearer merge-base); if unsure, ask the user.
- Compute the fork point once and reuse it: `git merge-base <base> HEAD`.
- List what will be squashed so the user sees the scope:
  `git log --format='%h %s' $(git merge-base <base> HEAD)..HEAD`
- If that list has **0 or 1** commits, stop and say so — nothing to squash.

## 3. Reset and write the squashed commit message

First collapse the branch, then write the message from the full branch diff:

1. `git reset --soft $(git merge-base <base> HEAD)` — moves the branch pointer to the fork point; all the branch's changes are now staged, working tree unchanged.
2. Run `git diff --cached` to see the complete branch diff now staged, and write one Conventional Commits message covering the whole branch, in this shape:

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

If any commit subject being squashed carried a `!` breaking-change marker or a `BREAKING CHANGE:` footer, make sure the squashed message preserves it — double-check for branch-level breaking changes that span commits.

## 4. Commit

Commit with one `-m` per blank-line-separated block — `git commit -m "<subject>"`, plus `-m "<body>"` and `-m "<footer>"` blocks when present.

## 5. Report

- Run `git log -1 --oneline` and show it.
- Check whether the branch has an upstream: `git rev-parse --abbrev-ref --symbolic-full-name @{u}` (may fail if none). If it does, the local and remote have now diverged — tell the user they'll need `git push --force-with-lease` to update it, and offer to run it. **Never push automatically.**

Rules:
- Never `git push` without explicit confirmation.
- The soft reset never touches the working tree, so file changes are always preserved — if anything looks off, `git reflog` recovers the pre-squash state.

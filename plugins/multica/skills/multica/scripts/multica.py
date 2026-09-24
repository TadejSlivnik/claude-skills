#!/usr/bin/env python3
"""Multica cloud: read issues, dispatch agents, push instructions, diagnose runs.

Usage:
  multica.py issue get <KEY|url|id> [profile] [--comments N] [--json]
  multica.py issue comment <KEY|url|id> (--file path | --text "...") [--profile p]
  multica.py issue dispatch <KEY|url|id> --to <AgentName> [--comment-file path]
                            [--profile p] [--force] [--dry-run]
  multica.py issue create --title "..." [--project name|id] [--parent KEY]
                          [--stage N] [--description-file path] [--status todo]
                          [--assign <AgentName>] [--profile p]
  multica.py agents list [--profile p]
  multica.py agents push [Name ...] [--profile p] [--dry-run]
  multica.py runs [--agent Name] [--failed] [--limit N] [--profile p]
  multica.py runs cancel <task-id> [--profile p]
  multica.py status [--hours N] [--profile p]
  multica.py profiles

Auth: profiles live in ~/.config/multica/profiles.json (override with
$MULTICA_PROFILES). See SKILL.md for format. Falls back to MULTICA_TOKEN
(+ MULTICA_WORKSPACE_ID, MULTICA_API_BASE) when no config file is present.

Each profile may set "api_base" to point at a self-hosted instance; it defaults
to the cloud. A profile is one instance + one workspace, so cloud and self-hosted
live side by side as separate profiles.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

DEFAULT_API = "https://api.multica.ai/api"


# ---- shared ----------------------------------------------------------------

def config_path():
    p = os.environ.get("MULTICA_PROFILES")
    return os.path.expanduser(p or "~/.config/multica/profiles.json")


def load_config():
    path = config_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        sys.exit(f"ERROR: could not read profiles at {path}: {e}")


def resolve_profile(requested):
    """Explicit --profile wins; else the single configured profile; else env fallback."""
    cfg = load_config()
    if not cfg:
        token = os.environ.get("MULTICA_TOKEN")
        if not token:
            sys.exit(
                f"ERROR: no config at {config_path()} and MULTICA_TOKEN is unset.\n"
                "See SKILL.md > Setup — offer to create the profiles file."
            )
        return {
            "token": token,
            "workspace_id": os.environ.get("MULTICA_WORKSPACE_ID", ""),
            "agents_dir": os.environ.get("MULTICA_AGENTS_DIR", ""),
            "api_base": os.environ.get("MULTICA_API_BASE", DEFAULT_API),
        }
    profiles = cfg.get("profiles") or {}
    if not profiles:
        sys.exit(f"ERROR: no profiles defined in {config_path()}")
    if requested:
        if requested not in profiles:
            sys.exit(f"ERROR: no profile '{requested}'. Have: {', '.join(profiles)}")
        return profiles[requested]
    if len(profiles) == 1:
        return next(iter(profiles.values()))
    sys.exit(
        f"ERROR: several profiles ({', '.join(profiles)}) — pass --profile. "
        "Do not guess which one the user meant."
    )


def api_base(prof):
    """Where this profile's Multica lives — cloud by default, or a self-hosted host."""
    return (prof.get("api_base") or DEFAULT_API).rstrip("/")


def http(path, prof, body=None, method=None):
    url = path if path.startswith("http") else api_base(prof) + path
    headers = {"Authorization": "Bearer " + prof["token"]}
    if prof.get("workspace_id"):
        headers["X-Workspace-ID"] = prof["workspace_id"]
    data = None
    if method is None:
        method = "POST" if body is not None else "GET"
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        sys.exit(f"ERROR: {method} {url} -> HTTP {e.code}\n{detail}")
    except urllib.error.URLError as e:
        sys.exit(f"ERROR: {method} {url} -> {e.reason}")


def parse_flags(argv):
    """--key value / --flag -> (positionals, {key: value|True})."""
    pos, flags, i = [], {}, 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            key = a[2:]
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                flags[key] = argv[i + 1]
                i += 2
            else:
                flags[key] = True
                i += 1
        else:
            pos.append(a)
            i += 1
    return pos, flags


def emit(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def read_body(flags, file_key, text_key=None):
    if flags.get(file_key):
        with open(os.path.expanduser(flags[file_key]), encoding="utf-8") as f:
            return f.read()
    if text_key and flags.get(text_key):
        return flags[text_key]
    return None


def status_of(issue):
    """Display label: the custom status name if there is one, else the category."""
    name = issue.get("status_name")
    if name:
        return f"{name} ({status_category(issue)})"
    s = issue.get("status")
    if isinstance(s, dict):
        return s.get("name") or s.get("category") or ""
    return s or ""


def status_category(issue):
    """One of: backlog todo in_progress in_review blocked done cancelled.

    Custom statuses are pinned to one of these seven, so the category is what
    decides behaviour (e.g. whether an assignment can trigger a run) — never the
    display name, which the user is free to rename.
    """
    cat = issue.get("status_category")
    if cat:
        return cat.lower()
    s = issue.get("status")
    if isinstance(s, dict):
        return (s.get("category") or s.get("name") or "").lower()
    return (s or "").lower()


# ---- resolution ------------------------------------------------------------

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]*-\d+)\b")


def all_issues(prof, limit=200):
    d = http(f"/issues?limit={limit}", prof)
    return d.get("issues", d.get("data", d)) if isinstance(d, dict) else d


def resolve_issue(ref, prof):
    """Accept a UUID, a WEBS-41 key, or an issue URL from any host.

    The key is found by regex, so a self-hosted URL works as well as a cloud one.
    """
    ref = (ref or "").strip()
    if UUID_RE.match(ref):
        d = http(f"/issues/{ref}", prof)
        return d.get("issue", d)
    m = KEY_RE.search(ref.upper())
    if not m:
        sys.exit(f"ERROR: cannot parse an issue key or id from '{ref}'")
    key = m.group(1)
    for i in all_issues(prof):
        if i.get("identifier") == key:
            d = http(f"/issues/{i['id']}", prof)
            return d.get("issue", d)
    sys.exit(f"ERROR: no issue '{key}' in this workspace (searched the 200 most recent)")


def all_agents(prof):
    d = http("/agents", prof)
    return d if isinstance(d, list) else d.get("agents", [])


def resolve_agent(name, prof):
    agents = all_agents(prof)
    for a in agents:
        if a["name"].lower() == name.lower():
            return a
    sys.exit(f"ERROR: no agent '{name}'. Have: {', '.join(a['name'] for a in agents)}")


def comments_of(issue_id, prof):
    d = http(f"/issues/{issue_id}/comments", prof)
    return d if isinstance(d, list) else d.get("comments", d.get("data", []))


# ---- issue commands --------------------------------------------------------

def issue_get(argv):
    pos, flags = parse_flags(argv)
    if not pos:
        sys.exit("usage: issue get <KEY|url|id> [profile] [--comments N]")
    prof = resolve_profile(flags.get("profile") or (pos[1] if len(pos) > 1 else None))
    issue = resolve_issue(pos[0], prof)
    cs = comments_of(issue["id"], prof)
    n = int(flags.get("comments", 5))
    if flags.get("json"):
        emit({"issue": issue, "comments": cs})
        return
    print(f"{issue.get('identifier')}  {issue.get('title')}")
    print(f"  id        {issue['id']}")
    print(f"  status    {status_of(issue)}")
    print(f"  assignee  {issue.get('assignee_type')} {issue.get('assignee_id')}")
    print(f"  parent    {issue.get('parent_issue_id')}")
    print(f"  stage     {issue.get('stage')}")
    print(f"  project   {issue.get('project_id')}")
    print(f"\n--- description ---\n{issue.get('description') or '(none)'}")
    print(f"\n--- comments: {len(cs)} total, showing last {min(n, len(cs))} ---")
    for c in cs[-n:] if n else []:
        print(f"\n[{c.get('created_at')}] {c.get('author_type')}")
        print(c.get("content", ""))


def issue_comment(argv):
    pos, flags = parse_flags(argv)
    if not pos:
        sys.exit("usage: issue comment <KEY|url|id> (--file path | --text \"...\")")
    prof = resolve_profile(flags.get("profile"))
    body = read_body(flags, "file", "text")
    if not body:
        sys.exit("ERROR: pass --file or --text")
    issue = resolve_issue(pos[0], prof)
    warn_if_agent_assigned(issue, prof)
    http(f"/issues/{issue['id']}/comments", prof, {"content": body})
    print(f"commented on {issue['identifier']}")


def warn_if_agent_assigned(issue, prof):
    """A comment by anyone else on an issue assigned to an agent WAKES that agent."""
    if issue.get("assignee_type") == "agent" and issue.get("assignee_id"):
        who = next((a["name"] for a in all_agents(prof)
                    if a["id"] == issue["assignee_id"]), issue["assignee_id"])
        print(
            f"NOTE: {issue['identifier']} is assigned to {who} — this comment dispatches "
            f"a run. That is a real trigger, not just a note.",
            file=sys.stderr,
        )


def issue_dispatch(argv):
    """The safe handoff: comment first, then assign exactly once."""
    pos, flags = parse_flags(argv)
    if not pos or not flags.get("to"):
        sys.exit("usage: issue dispatch <KEY|url|id> --to <AgentName> [--comment-file path]")
    prof = resolve_profile(flags.get("profile"))
    issue = resolve_issue(pos[0], prof)
    agent = resolve_agent(flags["to"], prof)
    note = read_body(flags, "comment-file")

    # Guard 1 — a no-op re-assign fires nothing and the work stalls silently.
    if issue.get("assignee_id") == agent["id"]:
        msg = (
            f"REFUSED: {issue['identifier']} is already assigned to {agent['name']}.\n"
            "Re-assigning to the same agent is a no-op — no run fires. To wake it, post a\n"
            "comment instead (that IS the trigger for an already-assigned agent):\n"
            f"  multica.py issue comment {issue['identifier']} --file <note.md>"
        )
        if not flags.get("force"):
            sys.exit(msg)
        print("WARNING (--force): " + msg, file=sys.stderr)

    # Guard 2 — backlog issues never dispatch on assignment.
    cat = status_category(issue)
    if cat == "backlog":
        if not flags.get("force"):
            sys.exit(
                f"REFUSED: {issue['identifier']} is in backlog — assignment never triggers "
                "a run from there.\nMove it to todo first, then dispatch."
            )
        print("WARNING (--force): dispatching from backlog; no run will fire.", file=sys.stderr)

    if flags.get("dry-run"):
        print(f"DRY RUN\n  1. {'POST comment' if note else '(no comment)'}"
              f"\n  2. PUT assignee -> {agent['name']} ({agent['id']})")
        return

    # Order matters: comment BEFORE assigning. A comment posted after the assignment
    # is a second, independent trigger and fires a duplicate run.
    if note:
        http(f"/issues/{issue['id']}/comments", prof, {"content": note})
        print(f"commented on {issue['identifier']}")

    http(f"/issues/{issue['id']}", prof,
         {"assignee_type": "agent", "assignee_id": agent["id"]}, method="PUT")

    after = http(f"/issues/{issue['id']}", prof)
    after = after.get("issue", after)
    if after.get("assignee_id") == agent["id"]:
        print(f"dispatched {issue['identifier']} -> {agent['name']}")
    else:
        print(f"WARNING: assignee did not change on {issue['identifier']} — no run fired.",
              file=sys.stderr)


def issue_create(argv):
    pos, flags = parse_flags(argv)
    if not flags.get("title"):
        sys.exit("usage: issue create --title \"...\" [--project x] [--parent KEY] [--stage N]")
    prof = resolve_profile(flags.get("profile"))
    body = {"title": flags["title"]}
    desc = read_body(flags, "description-file", "description")
    if desc:
        body["description"] = desc
    if flags.get("project"):
        body["project_id"] = resolve_project(flags["project"], prof)
    if flags.get("parent"):
        body["parent_id"] = resolve_issue(flags["parent"], prof)["id"]
    if flags.get("stage"):
        body["stage"] = int(flags["stage"])
    created = http("/issues", prof, body)
    created = created.get("issue", created)
    print(f"created {created.get('identifier')}  {created['id']}")

    # Assignment never triggers from backlog, so make sure we are out of it first.
    want = flags.get("status")
    if not want and flags.get("assign") and status_category(created) == "backlog":
        want = "todo"
    if want:
        http(f"/issues/{created['id']}", prof, {"status": want}, method="PUT")
        print(f"  status -> {want}")
    if flags.get("assign"):
        agent = resolve_agent(flags["assign"], prof)
        http(f"/issues/{created['id']}", prof,
             {"assignee_type": "agent", "assignee_id": agent["id"]}, method="PUT")
        print(f"  dispatched -> {agent['name']}")


def resolve_project(ref, prof):
    if UUID_RE.match(ref):
        return ref
    d = http("/projects", prof)
    projects = d if isinstance(d, list) else d.get("projects", [])
    for p in projects:
        if (p.get("title") or "").lower() == ref.lower():
            return p["id"]
    sys.exit(f"ERROR: no project '{ref}'. Have: "
             f"{', '.join(p.get('title', '?') for p in projects)}")


# ---- agent commands --------------------------------------------------------

STANDALONE_MARKER = "<!-- standalone -->"


def agents_dir(prof):
    d = prof.get("agents_dir")
    if not d:
        sys.exit("ERROR: this profile has no 'agents_dir'. Add it to "
                 f"{config_path()} — the directory holding _conventions.md and <agent>.md")
    d = os.path.expanduser(d)
    if not os.path.isdir(d):
        sys.exit(f"ERROR: agents_dir does not exist: {d}")
    return d


def agents_list(argv):
    _, flags = parse_flags(argv)
    prof = resolve_profile(flags.get("profile"))
    for a in all_agents(prof):
        print(f"{a['name']:<12} {a.get('model'):<18} {a['id']}")


def agents_push(argv):
    """Upload _conventions.md + <agent>.md as each agent's Instructions, then verify.

    Conventions are prepended unless the agent file's first line is the standalone
    marker. Agent ids are resolved by name at call time — never cached.
    """
    names, flags = parse_flags(argv)
    prof = resolve_profile(flags.get("profile"))
    d = agents_dir(prof)

    conv_path = os.path.join(d, "_conventions.md")
    if not os.path.exists(conv_path):
        sys.exit(f"ERROR: no _conventions.md in {d}")
    conv = open(conv_path, encoding="utf-8").read()

    live = {a["name"].lower(): a for a in all_agents(prof)}
    files = {}
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".md") or fn.startswith("_") or fn == "README.md":
            continue
        files[os.path.splitext(fn)[0].lower()] = os.path.join(d, fn)

    wanted = [n.lower() for n in names] if names else list(files)
    missing = [n for n in wanted if n not in files]
    if missing:
        sys.exit(f"ERROR: no file for: {', '.join(missing)} in {d}")

    rc = 0
    for name in wanted:
        path = files[name]
        own = open(path, encoding="utf-8").read()
        standalone = own.lstrip().startswith(STANDALONE_MARKER)
        instructions = own if standalone else conv + "\n\n---\n\n" + own

        agent = live.get(name)
        if not agent:
            print(f"{name:<12} SKIP   no agent named '{name}' in the workspace")
            rc = 1
            continue
        tag = "standalone" if standalone else "conventions"
        if flags.get("dry-run"):
            print(f"{agent['name']:<12} DRY    {len(instructions)}ch  ({tag})")
            continue

        http(f"/agents/{agent['id']}", prof, {"instructions": instructions}, method="PUT")
        # Accepted != stored on this API — read back rather than trusting the 200.
        back = http(f"/agents/{agent['id']}", prof)
        back = back.get("agent", back)
        ok = (back.get("instructions") or "") == instructions
        print(f"{agent['name']:<12} {'OK' if ok else 'MISMATCH'}   "
              f"{len(instructions)}ch  ({tag})")
        if not ok:
            rc = 1
    sys.exit(rc)


# ---- run commands ----------------------------------------------------------

def runs(argv):
    pos, flags = parse_flags(argv)
    if pos and pos[0] == "cancel":
        return runs_cancel(pos[1:], flags)
    prof = resolve_profile(flags.get("profile"))
    limit = int(flags.get("limit", 3))
    agents = all_agents(prof)
    if flags.get("agent"):
        agents = [resolve_agent(flags["agent"], prof)]
    rows = []
    for a in agents:
        d = http(f"/agents/{a['id']}/tasks", prof)
        ts = d if isinstance(d, list) else d.get("tasks", [])
        for t in ts[:limit]:
            err = t.get("error") or (t.get("result") or {}).get("error") or ""
            if flags.get("failed") and t.get("status") not in ("failed", "cancelled"):
                continue
            rows.append((t.get("created_at", ""), a["name"], t.get("status", ""),
                         t.get("kind", ""), t.get("id", ""), str(err)[:90]))
    for r in sorted(rows, reverse=True):
        print(f"{r[0]}  {r[1]:<12} {r[2]:<10} {r[3]:<8} {r[4]}  {r[5]}")
    if not rows:
        print("no runs matched")


def runs_cancel(pos, flags):
    if not pos:
        sys.exit("usage: runs cancel <task-id>")
    prof = resolve_profile(flags.get("profile"))
    http(f"/tasks/{pos[0]}/cancel", prof, {})
    print(f"cancelled {pos[0]}")


def status(argv):
    """One-shot health check: runtime online, CLI version, recent failures."""
    _, flags = parse_flags(argv)
    prof = resolve_profile(flags.get("profile"))
    hours = int(flags.get("hours", 24))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    print(f"INSTANCE  {api_base(prof)}")
    d = http("/runtimes", prof)
    rts = d if isinstance(d, list) else d.get("runtimes", [])
    print("\nRUNTIMES")
    for r in rts:
        print(f"  {r.get('name'):<18} {r.get('status'):<9} {r.get('device_info')}")
        print(f"  {'':<18} last seen {r.get('last_seen_at') or r.get('updated_at')}")
    if not any(r.get("status") == "online" for r in rts):
        print("  !! no runtime online — nothing will run")

    print(f"\nFAILED RUNS (last {hours}h)")
    found = 0
    for a in all_agents(prof):
        d = http(f"/agents/{a['id']}/tasks", prof)
        ts = d if isinstance(d, list) else d.get("tasks", [])
        for t in ts[:10]:
            if t.get("status") != "failed":
                continue
            when = t.get("created_at", "")
            try:
                if datetime.fromisoformat(when.replace("Z", "+00:00")) < cutoff:
                    continue
            except ValueError:
                pass
            err = t.get("error") or (t.get("result") or {}).get("error") or ""
            print(f"  {when}  {a['name']:<12} {str(err)[:110]}")
            found += 1
    if not found:
        print("  none")


def cmd_profiles():
    cfg = load_config()
    if not cfg:
        print(f"no config at {config_path()}; "
              f"MULTICA_TOKEN is {'set' if os.environ.get('MULTICA_TOKEN') else 'unset'}")
        return
    for name, p in (cfg.get("profiles") or {}).items():
        print(f"{name:<12} {api_base(p)}")
        print(f"{'':<12}   workspace={p.get('workspace_id', '?')} "
              f"agents_dir={p.get('agents_dir', '-')}")


# ---- entry -----------------------------------------------------------------

def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    group, rest = argv[0], argv[1:]
    if group == "issue":
        if not rest:
            sys.exit("usage: issue (get|comment|dispatch|create) ...")
        sub, rest = rest[0], rest[1:]
        return {"get": issue_get, "comment": issue_comment,
                "dispatch": issue_dispatch, "create": issue_create}.get(
                    sub, lambda a: sys.exit(f"unknown: issue {sub}"))(rest)
    if group == "agents":
        if not rest:
            sys.exit("usage: agents (list|push) ...")
        sub, rest = rest[0], rest[1:]
        return {"list": agents_list, "push": agents_push}.get(
            sub, lambda a: sys.exit(f"unknown: agents {sub}"))(rest)
    if group == "runs":
        return runs(rest)
    if group == "status":
        return status(rest)
    if group == "profiles":
        return cmd_profiles()
    sys.exit(f"unknown command: {group}\n{__doc__}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Multica cloud: read issues, dispatch agents, push instructions, diagnose runs.

Usage:
  multica.py issue get <KEY|url|id> [profile] [--comments N] [--json]
  multica.py issue comment <KEY|url|id> (--file path | --text "...") [--profile p]
  multica.py issue dispatch <KEY|url|id> --to <AgentName> [--comment-file path]
                            [--profile p] [--force] [--dry-run]
  multica.py issue create --title "..." [--project name|id] [--label name ...]
                          [--priority none|low|medium|high|urgent] [--due DATE]
                          [--parent KEY] [--stage N] [--description-file path]
                          [--status todo] [--assign <AgentName>] [--profile p]
  multica.py issue label <KEY|url|id> [--add name ...] [--remove name ...]
  multica.py labels [--json] [--profile p]
  multica.py agents list [--profile p]
  multica.py agents push [Name ...] [--profile p] [--dry-run]
  multica.py workspace show [--profile p]
  multica.py workspace (pull|push) [--profile p] [--dry-run] [--force]
  multica.py project list [--profile p]
  multica.py project show <name> [--profile p]
  multica.py project (pull|push) [name ...] [--profile p] [--dry-run] [--force]
  multica.py runs [--agent Name] [--failed] [--limit N] [--profile p]
  multica.py runs cancel <task-id> [--profile p]
  multica.py status [--hours N] [--profile p]
  multica.py profiles

Auth: profiles live in ~/.config/multica/profiles.json (override with
$MULTICA_PROFILES). See SKILL.md for format. Falls back to MULTICA_TOKEN
(+ MULTICA_WORKSPACE_ID, MULTICA_API_BASE) when no config file is present.

Instruction text lives in files, never only on the server. agents_dir holds
_conventions.md and <agent>.md. Beside it, context/workspace.md is the workspace
context and context/projects/<title>.md is each project description — both
injected by the platform into every agent brief. Override with "context_dir".
Always `pull` before the first `push`: it seeds the files from the live values.

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
                val = argv[i + 1]
                if key in flags:            # repeated flag -> list, for --label
                    prev = flags[key]
                    flags[key] = (prev if isinstance(prev, list) else [prev]) + [val]
                else:
                    flags[key] = val
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


def flag_list(flags, key):
    """--label a --label b and --label a,b both mean [a, b]."""
    raw = flags.get(key)
    if not raw or raw is True:
        return []
    items = raw if isinstance(raw, list) else [raw]
    return [x.strip() for i in items for x in i.split(",") if x.strip()]


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
    # Labels are gate config in a squad workspace, so never read an issue without them.
    print(f"  labels    {', '.join(l['name'] for l in (issue.get('labels') or [])) or '-'}")
    print(f"  priority  {issue.get('priority')}"
          + (f"   due {issue['due_date']}" if issue.get("due_date") else ""))
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


PRIORITIES = ("none", "low", "medium", "high", "urgent")


def issue_create(argv):
    """Create an issue, then fill in everything the create body refuses to take.

    The create body is strictly validated — an unknown field is a 400, not a
    silent drop — and it takes neither labels nor priority. Both are separate
    calls afterwards, which makes ORDER the thing to get right: labels, priority
    and dates all land BEFORE the assignment, because assigning is what starts
    the run. An agent that wakes to an unlabelled issue has already read the
    wrong gate config by the time the label arrives.
    """
    pos, flags = parse_flags(argv)
    if not flags.get("title"):
        sys.exit('usage: issue create --title "..." [--project x] [--label l ...] '
                 "[--priority p] [--due YYYY-MM-DD] [--parent KEY] [--stage N] "
                 "[--assign Agent]")
    prof = resolve_profile(flags.get("profile"))

    # Resolve every reference before writing anything: a typo'd label should not
    # leave a half-configured issue behind.
    label_ids = [resolve_label(n, prof) for n in flag_list(flags, "label")]
    priority = (flags.get("priority") or "").lower() or None
    if priority and priority not in PRIORITIES:
        sys.exit(f"ERROR: priority '{priority}' is not one of {', '.join(PRIORITIES)}")

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
    iid = created["id"]
    print(f"created {created.get('identifier')}  {iid}")

    # One POST per label — the API takes exactly one at a time.
    for name, lid in zip(flag_list(flags, "label"), label_ids):
        http(f"/issues/{iid}/labels", prof, {"label_id": lid})
        print(f"  label -> {name}")
    patch = {}
    if priority:
        patch["priority"] = priority
    if flags.get("due"):
        patch["due_date"] = flags["due"]
    if patch:
        http(f"/issues/{iid}", prof, patch, method="PUT")
        print("  " + ", ".join(f"{k} -> {v}" for k, v in patch.items()))

    # Assignment never triggers from backlog, so make sure we are out of it first.
    want = flags.get("status")
    if not want and flags.get("assign") and status_category(created) == "backlog":
        want = "todo"
    if want:
        http(f"/issues/{iid}", prof, {"status": want}, method="PUT")
        print(f"  status -> {want}")

    # Last, because this is the call that starts a run.
    if flags.get("assign"):
        agent = resolve_agent(flags["assign"], prof)
        http(f"/issues/{iid}", prof,
             {"assignee_type": "agent", "assignee_id": agent["id"]}, method="PUT")
        print(f"  dispatched -> {agent['name']}")

    if label_ids or patch:
        back = http(f"/issues/{iid}", prof)
        back = back.get("issue", back)
        print(f"  verified: labels={[l['name'] for l in (back.get('labels') or [])]} "
              f"priority={back.get('priority')} due={back.get('due_date')}")


def issue_label(argv):
    """Add or remove labels on an existing issue. Neither call wakes an agent."""
    pos, flags = parse_flags(argv)
    if not pos:
        sys.exit('usage: issue label <KEY> [--add l ...] [--remove l ...]')
    prof = resolve_profile(flags.get("profile"))
    issue = resolve_issue(pos[0], prof)
    add, remove = flag_list(flags, "add"), flag_list(flags, "remove")
    if not add and not remove:
        sys.exit("nothing to do: pass --add and/or --remove")
    for name in add:
        http(f"/issues/{issue['id']}/labels", prof,
             {"label_id": resolve_label(name, prof)})
        print(f"  + {name}")
    for name in remove:
        http(f"/issues/{issue['id']}/labels/{resolve_label(name, prof)}",
             prof, method="DELETE")
        print(f"  - {name}")
    back = http(f"/issues/{issue['id']}", prof)
    back = back.get("issue", back)
    print(f"{issue['identifier']} labels: "
          f"{', '.join(l['name'] for l in (back.get('labels') or [])) or '(none)'}")


def all_labels(prof):
    d = http("/labels", prof)
    return d if isinstance(d, list) else d.get("labels", [])


def resolve_label(ref, prof):
    if UUID_RE.match(ref):
        return ref
    labels = all_labels(prof)
    for l in labels:
        if (l.get("name") or "").lower() == ref.lower():
            return l["id"]
    sys.exit(f"ERROR: no label '{ref}'. Have: "
             f"{', '.join(l.get('name', '?') for l in labels)}")


def labels_list(argv):
    """The menu to offer before creating anything — names, colours and meaning."""
    _, flags = parse_flags(argv)
    prof = resolve_profile(flags.get("profile"))
    labels = all_labels(prof)
    if flags.get("json"):
        return emit(labels)
    if not labels:
        return print("(no labels in this workspace)")
    for l in labels:
        print(f"{l.get('name'):<24} {l.get('color', ''):<9} used {l.get('usage_count', 0)}")
        if l.get("description"):
            print(f"  {l['description']}")


def resolve_project(ref, prof):
    if UUID_RE.match(ref):
        return ref
    projects = all_projects(prof)
    for p in projects:
        if (p.get("title") or "").lower() == ref.lower():
            return p["id"]
    sys.exit(f"ERROR: no project '{ref}'. Have: "
             f"{', '.join(p.get('title', '?') for p in projects)}")


# ---- agent commands --------------------------------------------------------

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
    """Upload <agent>.md as that agent's Instructions, then verify.

    Role only. Everything shared across agents belongs in the workspace context and
    everything project-specific in the project description — the platform injects both
    into every brief, so prepending them here would ship them twice. Agent ids are
    resolved by name at call time, never cached.
    """
    names, flags = parse_flags(argv)
    prof = resolve_profile(flags.get("profile"))
    d = agents_dir(prof)

    stale = os.path.join(d, "_conventions.md")
    if os.path.exists(stale):
        sys.exit(f"ERROR: {stale} still exists but is no longer used. Its content belongs "
                 "in context/workspace.md ('workspace push'). Delete it to confirm the "
                 "move, or agents will silently lose it.")

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
        instructions = open(path, encoding="utf-8").read()

        agent = live.get(name)
        if not agent:
            print(f"{name:<12} SKIP   no agent named '{name}' in the workspace")
            rc = 1
            continue
        if flags.get("dry-run"):
            live_len = len(agent.get("instructions") or "")
            note = "no change" if live_len == len(instructions) else f"live is {live_len}ch"
            print(f"{agent['name']:<12} DRY    {len(instructions)}ch  ({note})")
            continue

        http(f"/agents/{agent['id']}", prof, {"instructions": instructions}, method="PUT")
        # Accepted != stored on this API — read back rather than trusting the 200.
        back = http(f"/agents/{agent['id']}", prof)
        back = back.get("agent", back)
        ok = (back.get("instructions") or "") == instructions
        print(f"{agent['name']:<12} {'OK' if ok else 'MISMATCH'}   "
              f"{len(instructions)}ch")
        if not ok:
            rc = 1
    sys.exit(rc)


# ---- workspace and project context -----------------------------------------
#
# Two injection slots the platform renders into every agent brief:
#   workspace.context    -> "## Workspace Context", every agent, every task kind
#   project.description  -> "## Project Context", every agent working that project
# Both are injected, not fetched, so an agent cannot skip them. Keeping them in
# git and pushing from here is what stops them drifting the way agent files did.

def context_dir(prof, create=False):
    """Where workspace.md and projects/*.md live.

    Defaults to <parent of agents_dir>/context, so a profile already pointing
    at .../multica/agents needs no new key.
    """
    d = prof.get("context_dir")
    if not d:
        ad = prof.get("agents_dir")
        if not ad:
            sys.exit("ERROR: this profile has neither 'context_dir' nor 'agents_dir'. "
                     f"Add one to {config_path()}")
        # Its own directory, never beside the repo docs: a bare workspace.md
        # collides with WORKSPACE.md on a case-insensitive filesystem and not on
        # a case-sensitive one, which is the worse of the two failures.
        d = os.path.join(os.path.dirname(os.path.expanduser(ad).rstrip("/")),
                         "context")
    d = os.path.expanduser(d)
    if not os.path.isdir(d):
        if create:
            os.makedirs(d, exist_ok=True)
        else:
            sys.exit(f"ERROR: no context directory at {d} — run 'project pull' or "
                     "'workspace pull' first; they seed it from the live values.")
    return d


def workspace_file(prof, create=False):
    return os.path.join(context_dir(prof, create), "workspace.md")


def projects_dir(prof, must_exist=True):
    d = os.path.join(context_dir(prof, create=not must_exist), "projects")
    if must_exist and not os.path.isdir(d):
        sys.exit(f"ERROR: no projects directory at {d} — run 'project pull' first; "
                 "it seeds the files from the live descriptions so nothing is lost.")
    return d


def get_workspace(prof):
    wid = prof.get("workspace_id")
    if not wid:
        sys.exit("ERROR: this profile has no 'workspace_id'.")
    d = http(f"/workspaces/{wid}", prof)
    return d.get("workspace", d)


def all_projects(prof):
    d = http("/projects", prof)
    return d if isinstance(d, list) else d.get("projects", [])


def get_project(pid, prof):
    d = http(f"/projects/{pid}", prof)
    return d.get("project", d)


def _wanted_projects(names, prof):
    live = all_projects(prof)
    if not names:
        return sorted(live, key=lambda p: (p.get("title") or "").lower())
    by = {(p.get("title") or "").lower(): p for p in live}
    out, missing = [], []
    for n in names:
        p = by.get(n.lower())
        if p:
            out.append(p)
        else:
            missing.append(n)
    if missing:
        sys.exit(f"ERROR: no project: {', '.join(missing)}. Have: "
                 f"{', '.join(p.get('title', '?') for p in live)}")
    return out


def _read_local(path):
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def _write_local(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text + "\n")


# --- workspace ---

def workspace_show(argv):
    _, flags = parse_flags(argv)
    prof = resolve_profile(flags.get("profile"))
    w = get_workspace(prof)
    ctx = (w.get("context") or "").strip()
    print(f"# {w.get('name')} ({w.get('slug')})  prefix={w.get('issue_prefix')}")
    print(f"# context: {len(ctx)} chars — rendered as '## Workspace Context' "
          "in every agent brief\n")
    print(ctx or "(empty)")


def workspace_pull(argv):
    _, flags = parse_flags(argv)
    prof = resolve_profile(flags.get("profile"))
    ctx = (get_workspace(prof).get("context") or "").strip()
    path = workspace_file(prof, create=True)
    if os.path.exists(path):
        local = _read_local(path)
        if local == ctx:
            print(f"workspace.md  SAME    {len(ctx)}ch")
            return
        if not flags.get("force"):
            sys.exit(f"ERROR: {path} differs from live "
                     f"(local {len(local)}ch, live {len(ctx)}ch). "
                     "Pass --force to overwrite the local copy, or push instead.")
    _write_local(path, ctx)
    print(f"workspace.md  PULLED  {len(ctx)}ch -> {path}")


def workspace_push(argv):
    _, flags = parse_flags(argv)
    prof = resolve_profile(flags.get("profile"))
    path = workspace_file(prof)
    if not os.path.exists(path):
        sys.exit(f"ERROR: no workspace.md at {path}. Run 'workspace pull' first — "
                 "it seeds the file from the live value so nothing is lost.")
    text = _read_local(path)
    live = (get_workspace(prof).get("context") or "").strip()
    if flags.get("dry-run"):
        note = "no change" if live == text else f"live is {len(live)}ch"
        print(f"workspace     DRY     {len(text)}ch  ({note})")
        return
    if not text and live:
        sys.exit("ERROR: workspace.md is empty but the live context is not — "
                 "refusing to blank it. Delete it in the UI if that is what you want.")
    http(f"/workspaces/{prof['workspace_id']}", prof, {"context": text}, method="PUT")
    # Accepted != stored on this API — read back rather than trusting the 200.
    back = (get_workspace(prof).get("context") or "").strip()
    ok = back == text
    print(f"workspace     {'OK' if ok else 'MISMATCH'}      {len(text)}ch")
    sys.exit(0 if ok else 1)


# --- projects ---

def project_list(argv):
    _, flags = parse_flags(argv)
    prof = resolve_profile(flags.get("profile"))
    d = os.path.join(context_dir(prof, create=True), "projects")
    for p in _wanted_projects([], prof):
        desc = (p.get("description") or "").strip()
        path = os.path.join(d, f"{p.get('title')}.md")
        if os.path.exists(path):
            local = _read_local(path)
            state = "same" if local == desc else f"DIFFERS (local {len(local)}ch)"
        else:
            state = "no local file"
        print(f"{p.get('title'):<20} {len(desc):>5}ch  "
              f"res={p.get('resource_count')}  {state}")


def project_show(argv):
    names, flags = parse_flags(argv)
    if not names:
        sys.exit("usage: project show <name>")
    prof = resolve_profile(flags.get("profile"))
    p = _wanted_projects(names[:1], prof)[0]
    full = get_project(p["id"], prof)
    print(f"# {full.get('title')}  status={full.get('status')}  id={full['id']}")
    res = http(f"/projects/{p['id']}/resources", prof).get("resources") or []
    for r in res:
        ref = r.get("resource_ref") or {}
        print(f"# resource: {r.get('resource_type')}  {ref.get('url') or ref}")
    desc = (full.get("description") or "").strip()
    print(f"# description: {len(desc)} chars — rendered as '## Project Context'\n")
    print(desc or "(empty)")


def project_pull(argv):
    names, flags = parse_flags(argv)
    prof = resolve_profile(flags.get("profile"))
    d = projects_dir(prof, must_exist=False)
    os.makedirs(d, exist_ok=True)
    rc = 0
    for p in _wanted_projects(names, prof):
        desc = (p.get("description") or "").strip()
        path = os.path.join(d, f"{p.get('title')}.md")
        if os.path.exists(path):
            local = _read_local(path)
            if local == desc:
                print(f"{p['title']:<20} SAME    {len(desc)}ch")
                continue
            if not flags.get("force"):
                print(f"{p['title']:<20} DIFFERS local {len(local)}ch vs live "
                      f"{len(desc)}ch — not overwritten (--force to take live)")
                rc = 1
                continue
        _write_local(path, desc)
        print(f"{p['title']:<20} PULLED  {len(desc)}ch")
    sys.exit(rc)


def project_push(argv):
    names, flags = parse_flags(argv)
    prof = resolve_profile(flags.get("profile"))
    d = projects_dir(prof)
    rc = 0
    for p in _wanted_projects(names, prof):
        path = os.path.join(d, f"{p.get('title')}.md")
        if not os.path.exists(path):
            print(f"{p['title']:<20} SKIP    no {os.path.basename(path)} in {d}")
            continue
        text = _read_local(path)
        live = (p.get("description") or "").strip()
        if not text and live:
            print(f"{p['title']:<20} SKIP    file is empty but live is {len(live)}ch "
                  "— refusing to blank the description")
            rc = 1
            continue
        if flags.get("dry-run"):
            note = "no change" if live == text else f"live is {len(live)}ch"
            print(f"{p['title']:<20} DRY     {len(text)}ch  ({note})")
            continue
        http(f"/projects/{p['id']}", prof, {"description": text}, method="PUT")
        # Accepted != stored on this API — read back rather than trusting the 200.
        back = (get_project(p["id"], prof).get("description") or "").strip()
        ok = back == text
        print(f"{p['title']:<20} {'OK' if ok else 'MISMATCH'}      {len(text)}ch")
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
        print(f"{'':<12}   context_dir={p.get('context_dir') or '(beside agents_dir)'}")


# ---- entry -----------------------------------------------------------------

def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    group, rest = argv[0], argv[1:]
    if group == "issue":
        if not rest:
            sys.exit("usage: issue (get|comment|dispatch|create|label) ...")
        sub, rest = rest[0], rest[1:]
        return {"get": issue_get, "comment": issue_comment,
                "dispatch": issue_dispatch, "create": issue_create,
                "label": issue_label}.get(
                    sub, lambda a: sys.exit(f"unknown: issue {sub}"))(rest)
    if group == "agents":
        if not rest:
            sys.exit("usage: agents (list|push) ...")
        sub, rest = rest[0], rest[1:]
        return {"list": agents_list, "push": agents_push}.get(
            sub, lambda a: sys.exit(f"unknown: agents {sub}"))(rest)
    if group == "workspace":
        if not rest:
            sys.exit("usage: workspace (show|pull|push) ...")
        sub, rest = rest[0], rest[1:]
        return {"show": workspace_show, "pull": workspace_pull,
                "push": workspace_push}.get(
                    sub, lambda a: sys.exit(f"unknown: workspace {sub}"))(rest)
    if group == "project":
        if not rest:
            sys.exit("usage: project (list|show|pull|push) ...")
        sub, rest = rest[0], rest[1:]
        return {"list": project_list, "show": project_show,
                "pull": project_pull, "push": project_push}.get(
                    sub, lambda a: sys.exit(f"unknown: project {sub}"))(rest)
    if group == "labels":
        return labels_list(rest)
    if group == "runs":
        return runs(rest)
    if group == "status":
        return status(rest)
    if group == "profiles":
        return cmd_profiles()
    sys.exit(f"unknown command: {group}\n{__doc__}")


if __name__ == "__main__":
    main()

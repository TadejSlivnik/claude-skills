#!/usr/bin/env python3
"""ClickUp: read/write tasks and docs.

Usage:
  clickup.py task get <id|url> [profile]
  clickup.py task create --list <alias|id|url> --name "..." [--content-file path]
                         [--profile p] [--priority N] [--status S] [--tags a,b]
                         [--assignees id,...] [--due ms] [--dry-run]
  clickup.py task update <id|url> [profile] [--status S] [--priority N|none]
                         [--name "..."] [--content-file path] [--description "..."]
                         [--due ms|none] [--archived true|false]
                         [--add-assignees id,..] [--rem-assignees id,..]
                         [--add-tags a,b] [--rem-tags a,b] [--dry-run]
  clickup.py doc  get <id|url> [profile]
  clickup.py doc  create --name "..." [--content-file path] [--profile p]
                         [--parent <alias>] [--dry-run]
  clickup.py profiles

Auth: profiles live in ~/.config/clickup/profiles.json (override with
$CLICKUP_PROFILES). See SKILL.md for format. Fallback to CLICKUP_API_TOKEN
(+ CLICKUP_TEAM_ID) when no config file is present.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API2 = "https://api.clickup.com/api/v2"
API3 = "https://api.clickup.com/api/v3"


# ---- shared ----------------------------------------------------------------

def config_path():
    p = os.environ.get("CLICKUP_PROFILES")
    return os.path.expanduser(p or "~/.config/clickup/profiles.json")


def load_config():
    path = config_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        sys.exit(f"ERROR: could not read profiles at {path}: {e}")


def current_user_id(token):
    """Numeric id of the token's owner (the 'me' user)."""
    return http(f"{API2}/user", token)["user"]["id"]


def http(url, token, body=None, method=None):
    headers = {"Authorization": token}
    data = None
    if method is None:
        method = "POST" if body is not None else "GET"
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        sys.exit(f"ClickUp API error {e.code} for {url}: {detail}")
    except urllib.error.URLError as e:
        sys.exit(f"Network error reaching ClickUp: {e}")


def parse_flags(argv):
    """Minimal --key value / --flag parser -> dict (bare flags become True)."""
    out = {}
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok.startswith("--"):
            key = tok[2:]
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                out[key] = argv[i + 1]
                i += 2
            else:
                out[key] = True
                i += 1
        else:
            i += 1
    return out


def resolve_profile(cfg, requested, ws_from_url):
    if cfg is None:
        token = os.environ.get("CLICKUP_API_TOKEN")
        if not token:
            sys.exit(
                "ERROR: no profiles config and CLICKUP_API_TOKEN is not set.\n"
                f"Create {config_path()} (see SKILL.md) or export CLICKUP_API_TOKEN."
            )
        return {"token": token, "team_id": os.environ.get("CLICKUP_TEAM_ID")}

    profiles = cfg.get("profiles", {})
    if not profiles:
        sys.exit(f"ERROR: no profiles defined in {config_path()}")

    if requested:
        if requested not in profiles:
            sys.exit(
                f"ERROR: profile '{requested}' not found. "
                f"Available: {', '.join(sorted(profiles))}"
            )
        return profiles[requested]

    if ws_from_url:
        for prof in profiles.values():
            if str(prof.get("team_id")) == str(ws_from_url):
                return prof

    if len(profiles) == 1:
        return next(iter(profiles.values()))
    sys.exit(
        "ERROR: multiple profiles and none selected. Pass one as the trailing "
        f"argument. Available: {', '.join(sorted(profiles))}"
    )


def emit(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


# ---- task ------------------------------------------------------------------

def parse_task_ref(raw):
    """Return (task_id, team_from_url). URLs: .../t/<task> or .../t/<team>/<task>."""
    raw = raw.strip()
    if not raw.startswith("http"):
        return raw, None
    path = raw.split("?")[0].rstrip("/")
    parts = path.split("/t/")
    segs = parts[-1].split("/") if len(parts) > 1 else [path.split("/")[-1]]
    task = segs[-1]
    team = segs[0] if len(segs) > 1 else None
    return task, team


def resolve_list(value, profile):
    """alias in profile.lists -> id; URL -> id after /li/ or /l/; else raw id."""
    lists = profile.get("lists") or {}
    if value in lists:
        return str(lists[value])
    if value.startswith("http"):
        segs = value.split("?")[0].rstrip("/").split("/")
        for marker in ("li", "l"):
            if marker in segs:
                i = segs.index(marker)
                if i + 1 < len(segs):
                    return segs[i + 1]
        return segs[-1]
    return value


def task_get(args):
    if not args:
        sys.exit("Usage: clickup.py task get <id|url> [profile]")
    task_id, team_from_url = parse_task_ref(args[0])
    cfg = load_config()
    prof = resolve_profile(cfg, args[1] if len(args) > 1 else None, team_from_url)
    token = prof["token"]
    team = prof.get("team_id") or team_from_url

    qs = ""
    if "-" in task_id:
        if not team:
            sys.exit(
                f"ERROR: '{task_id}' looks like a custom task ID but no team_id "
                "is available for this profile."
            )
        qs = f"?custom_task_ids=true&team_id={team}"

    task = http(f"{API2}/task/{task_id}{qs}", token)
    comments = http(f"{API2}/task/{task_id}/comment{qs}", token).get("comments", [])

    priority = task.get("priority")
    emit({
        "id": task.get("id"),
        "custom_id": task.get("custom_id"),
        "name": task.get("name"),
        "status": (task.get("status") or {}).get("status"),
        "url": task.get("url"),
        "assignees": [a.get("username") for a in task.get("assignees", [])],
        "priority": priority.get("priority") if priority else None,
        "tags": [t.get("name") for t in task.get("tags", [])],
        "description": task.get("text_content") or task.get("description") or "",
        "comments": [
            {
                "by": (c.get("user") or {}).get("username"),
                "text": c.get("comment_text"),
                "date": c.get("date"),
            }
            for c in comments
        ],
    })


def task_create(argv):
    f = parse_flags(argv)
    if not f.get("list") or not f.get("name"):
        sys.exit('Usage: clickup.py task create --list <alias|id|url> --name "<title>" '
                 "[--profile p] [--content-file path] [--priority N] [--status S] "
                 "[--tags a,b] [--assignees me|id,...|none] [--due ms] [--dry-run]")

    cfg = load_config()
    prof = resolve_profile(cfg, f.get("profile"), None)
    list_id = resolve_list(f["list"], prof)

    body = {"name": f["name"]}
    if f.get("content-file"):
        with open(os.path.expanduser(f["content-file"]), encoding="utf-8") as fh:
            body["markdown_content"] = fh.read()
    if f.get("status"):
        body["status"] = f["status"]
    if f.get("priority"):
        body["priority"] = int(f["priority"])
    if f.get("tags"):
        body["tags"] = [t.strip() for t in f["tags"].split(",") if t.strip()]
    # Assignee resolution: default to the token owner ("me") unless the caller
    # opts out with `--assignees none`. `me` (alone or in a list) resolves to
    # the token owner; everything else is treated as a numeric user id.
    raw_assignees = f.get("assignees")
    if raw_assignees is None:
        body["assignees"] = [current_user_id(prof["token"])]
    elif str(raw_assignees).strip().lower() != "none":
        ids = []
        for a in str(raw_assignees).split(","):
            a = a.strip()
            if not a:
                continue
            ids.append(current_user_id(prof["token"]) if a.lower() == "me" else int(a))
        if ids:
            body["assignees"] = ids
    if f.get("due"):
        body["due_date"] = int(f["due"])

    endpoint = f"{API2}/list/{list_id}/task"
    if f.get("dry-run"):
        emit({"dry_run": True, "endpoint": f"POST {endpoint}", "body": body})
        return

    task = http(endpoint, prof["token"], body=body)
    emit({"id": task.get("id"), "url": task.get("url"),
          "name": task.get("name"), "list_id": list_id})


def task_update(argv):
    # First token is the task ref; an optional bare profile may follow; the
    # rest are --flags naming the fields to change.
    if not argv or argv[0].startswith("--"):
        sys.exit(USAGE_UPDATE)
    ref = argv[0]
    rest = argv[1:]
    profile = None
    if rest and not rest[0].startswith("--"):
        profile = rest[0]
        rest = rest[1:]
    f = parse_flags(rest)

    task_id, team_from_url = parse_task_ref(ref)
    cfg = load_config()
    prof = resolve_profile(cfg, f.get("profile") or profile, team_from_url)
    token = prof["token"]
    team = prof.get("team_id") or team_from_url

    qs = ""
    if "-" in task_id:
        if not team:
            sys.exit(f"ERROR: '{task_id}' looks like a custom task ID but no "
                     "team_id is available for this profile.")
        qs = f"?custom_task_ids=true&team_id={team}"

    # Fields settable via PUT /task/{id}
    body = {}
    if f.get("status"):
        body["status"] = f["status"]
    if f.get("priority") is not None and f.get("priority") is not True:
        p = f["priority"]
        body["priority"] = None if str(p).lower() in ("none", "clear", "null") else int(p)
    if f.get("name"):
        body["name"] = f["name"]
    if f.get("content-file"):
        with open(os.path.expanduser(f["content-file"]), encoding="utf-8") as fh:
            body["markdown_content"] = fh.read()
    if f.get("description"):
        body["description"] = f["description"]
    if f.get("due") is not None and f.get("due") is not True:
        d = f["due"]
        body["due_date"] = None if str(d).lower() in ("none", "clear", "null") else int(d)
    if f.get("archived") is not None:
        body["archived"] = str(f["archived"]).lower() in ("1", "true", "yes")

    def id_list(key):
        return [int(x) for x in str(f[key]).split(",") if x.strip()]

    assignee_obj = {}
    if f.get("add-assignees"):
        assignee_obj["add"] = id_list("add-assignees")
    if f.get("rem-assignees"):
        assignee_obj["rem"] = id_list("rem-assignees")
    if assignee_obj:
        body["assignees"] = assignee_obj

    add_tags = [t.strip() for t in str(f["add-tags"]).split(",")] if f.get("add-tags") else []
    rem_tags = [t.strip() for t in str(f["rem-tags"]).split(",")] if f.get("rem-tags") else []
    add_tags = [t for t in add_tags if t]
    rem_tags = [t for t in rem_tags if t]

    if not body and not add_tags and not rem_tags:
        sys.exit("ERROR: nothing to update. " + USAGE_UPDATE)

    task_url = f"{API2}/task/{task_id}{qs}"
    if f.get("dry-run"):
        steps = []
        if body:
            steps.append({"endpoint": f"PUT {task_url}", "body": body})
        for t in add_tags:
            steps.append({"endpoint": f"POST {API2}/task/{task_id}/tag/{urllib.parse.quote(t)}{qs}"})
        for t in rem_tags:
            steps.append({"endpoint": f"DELETE {API2}/task/{task_id}/tag/{urllib.parse.quote(t)}{qs}"})
        emit({"dry_run": True, "steps": steps})
        return

    result = {}
    if body:
        task = http(task_url, token, body=body, method="PUT")
        result = task
    for t in add_tags:
        http(f"{API2}/task/{task_id}/tag/{urllib.parse.quote(t)}{qs}", token, method="POST")
    for t in rem_tags:
        http(f"{API2}/task/{task_id}/tag/{urllib.parse.quote(t)}{qs}", token, method="DELETE")

    if not result:
        result = http(task_url, token)
    priority = result.get("priority")
    emit({
        "id": result.get("id") or task_id,
        "url": result.get("url"),
        "name": result.get("name"),
        "status": (result.get("status") or {}).get("status"),
        "priority": priority.get("priority") if priority else None,
        "assignees": [a.get("username") for a in result.get("assignees", [])],
        "tags": [t.get("name") for t in result.get("tags", [])],
    })


# ---- doc -------------------------------------------------------------------

def parse_doc_ref(raw):
    """Return (doc_id, workspace_from_url). URLs: .../<workspace>/v/dc/<doc_id>[/<page>]."""
    raw = raw.strip()
    if not raw.startswith("http"):
        return raw, None
    path = urllib.parse.urlsplit(raw).path.strip("/")
    segs = path.split("/")
    workspace = segs[0] if segs else None
    doc_id = None
    if "dc" in segs:
        i = segs.index("dc")
        if i + 1 < len(segs):
            doc_id = segs[i + 1]
    if not doc_id:
        doc_id = segs[-1]
    return doc_id, workspace


def resolve_parent(value, profile):
    """alias in profile.doc_parents -> {id, type}; type: 4=Space, 5=Folder, 6=List, 12=Doc."""
    parents = profile.get("doc_parents") or {}
    if value in parents:
        return parents[value]
    sys.exit(
        f"ERROR: doc parent '{value}' not found in profile's doc_parents. "
        f"Available: {', '.join(sorted(parents)) or '(none)'}"
    )


def flatten_pages(pages):
    out = []
    for p in pages or []:
        out.append({"id": p.get("id"), "name": p.get("name"), "content": p.get("content") or ""})
        if p.get("pages"):
            out.extend(flatten_pages(p["pages"]))
    return out


def doc_get(args):
    if not args:
        sys.exit("Usage: clickup.py doc get <id|url> [profile]")
    doc_id, ws_from_url = parse_doc_ref(args[0])
    cfg = load_config()
    prof = resolve_profile(cfg, args[1] if len(args) > 1 else None, ws_from_url)
    token = prof["token"]
    workspace = prof.get("team_id") or ws_from_url
    if not workspace:
        sys.exit(
            "ERROR: a workspace/team_id is required to fetch a Doc. Set team_id "
            "in the profile, or paste the full doc URL (it contains the workspace)."
        )

    doc = http(f"{API3}/workspaces/{workspace}/docs/{doc_id}", token)
    pages_url = (
        f"{API3}/workspaces/{workspace}/docs/{doc_id}/pages"
        "?max_page_depth=-1&content_format=text%2Fmd"
    )
    pages_resp = http(pages_url, token)
    raw_pages = pages_resp.get("pages") if isinstance(pages_resp, dict) else pages_resp

    emit({
        "id": doc.get("id") or doc_id,
        "name": doc.get("name"),
        "workspace_id": str(workspace),
        "pages": flatten_pages(raw_pages),
    })


def doc_create(argv):
    f = parse_flags(argv)
    if not f.get("name"):
        sys.exit('Usage: clickup.py doc create --name "<title>" --content-file <path> '
                 "[--profile p] [--parent <alias>] [--dry-run]")

    cfg = load_config()
    prof = resolve_profile(cfg, f.get("profile"), None)
    workspace = prof.get("team_id")
    if not workspace:
        sys.exit("ERROR: a workspace/team_id is required to create a Doc.")

    content = ""
    if f.get("content-file"):
        with open(os.path.expanduser(f["content-file"]), encoding="utf-8") as fh:
            content = fh.read()

    doc_body = {"name": f["name"], "visibility": "PRIVATE", "create_page": False}
    if f.get("parent"):
        doc_body["parent"] = resolve_parent(f["parent"], prof)
    page_body = {"name": f["name"], "content": content, "content_format": "text/md"}

    docs_url = f"{API3}/workspaces/{workspace}/docs"
    if f.get("dry-run"):
        emit({"dry_run": True,
              "step1": {"endpoint": f"POST {docs_url}", "body": doc_body},
              "step2": {"endpoint": f"POST {docs_url}/<new_doc_id>/pages", "body": page_body}})
        return

    doc = http(docs_url, prof["token"], body=doc_body)
    doc_id = doc.get("id")
    http(f"{docs_url}/{doc_id}/pages", prof["token"], body=page_body)
    emit({"id": doc_id, "url": doc.get("url"), "name": doc.get("name") or f["name"]})


# ---- main ------------------------------------------------------------------

USAGE = (
    "Usage:\n"
    "  clickup.py task get <id|url> [profile]\n"
    "  clickup.py task create --list <alias|id|url> --name \"...\" [...]\n"
    "  clickup.py task update <id|url> [profile] [--status S] [...]\n"
    "  clickup.py doc  get <id|url> [profile]\n"
    "  clickup.py doc  create --name \"...\" [...]\n"
    "  clickup.py profiles"
)

USAGE_UPDATE = (
    "Usage: clickup.py task update <id|url> [profile] "
    "[--status S] [--priority N|none] [--name \"...\"] [--content-file path] "
    "[--description \"...\"] [--due ms|none] [--archived true|false] "
    "[--add-assignees id,..] [--rem-assignees id,..] "
    "[--add-tags a,b] [--rem-tags a,b] [--dry-run]\n"
    "Notes: priority 1=urgent 2=high 3=normal 4=low (or 'none' to clear). "
    "Status names are list-specific (e.g. 'to do', 'ready to deploy'). "
    "Tags are added/removed individually; PUT does not replace the tag set."
)


def cmd_profiles():
    cfg = load_config()
    if cfg is None:
        print("(no config file; using CLICKUP_API_TOKEN env if set)")
    else:
        print("\n".join(sorted(cfg.get("profiles", {}))) or "(no profiles)")


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(USAGE)
    head = args[0]

    if head == "profiles":
        cmd_profiles()
        return

    dispatch = {
        ("task", "get"): task_get,
        ("task", "create"): task_create,
        ("task", "update"): task_update,
        ("doc", "get"): doc_get,
        ("doc", "create"): doc_create,
    }
    if head in ("task", "doc") and len(args) >= 2:
        fn = dispatch.get((head, args[1]))
        if fn:
            fn(args[2:])
            return

    sys.exit(USAGE)


if __name__ == "__main__":
    main()

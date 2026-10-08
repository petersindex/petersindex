"""Build dark_mode.svg and light_mode.svg from profile.json + ascii.txt.

    python scripts/generate.py            # fetch live GitHub stats (needs GH_TOKEN)
    python scripts/generate.py --offline  # reuse the last saved stats

Only the Python standard library is used, so it runs anywhere.
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.request
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "stats.json"

THEMES = {
    "dark": dict(bg="#161b22", text="#c9d1d9", key="#ffa657", value="#a5d6ff",
                 cc="#616e7f", add="#3fb950", dele="#f85149", ascii="#c9d1d9"),
    "light": dict(bg="#f6f8fa", text="#24292f", key="#953800", value="#0a3069",
                  cc="#c2cfde", add="#1a7f37", dele="#cf222e", ascii="#24292f"),
}

FONT_SIZE = 16
LINE_H = 20
CHAR_W = 9.65  # widest common monospace at 16px (Menlo / DejaVu); Consolas is narrower
PAD_X, PAD_Y = 24, 30
GAP = 3  # characters between the ascii art and the info column


# ---------------------------------------------------------------- GitHub stats

def gql(query, variables, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "profile-card"},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = json.load(r)
            if body.get("errors"):
                raise RuntimeError(body["errors"])
            return body["data"]
        except Exception as e:  # retry transient failures (502s are common on big queries)
            if attempt == 3:
                raise
            print(f"  retrying after error: {e}")
            time.sleep(3 * (attempt + 1))


USER_Q = """query($login: String!) {
  user(login: $login) {
    id
    followers { totalCount }
    owned: repositories(ownerAffiliations: OWNER) { totalCount }
    all: repositories(ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]) { totalCount }
  }
}"""

REPOS_Q = """query($login: String!, $after: String, $id: ID!, $aff: [RepositoryAffiliation]) {
  user(login: $login) {
    repositories(first: 50, after: $after, ownerAffiliations: $aff) {
      pageInfo { hasNextPage endCursor }
      nodes {
        nameWithOwner
        stargazerCount
        owner { login }
        defaultBranchRef { target { ... on Commit { history(author: {id: $id}) { totalCount } } } }
      }
    }
  }
}"""

HISTORY_Q = """query($owner: String!, $name: String!, $after: String, $id: ID!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { target { ... on Commit {
      history(first: 100, after: $after, author: {id: $id}) {
        pageInfo { hasNextPage endCursor }
        nodes { additions deletions }
      }
    } } }
  }
}"""


def fetch_stats(login, token, cache):
    print(f"Fetching stats for {login} ...")
    u = gql(USER_Q, {"login": login}, token)["user"]
    uid = u["id"]

    repos, after = [], None
    while True:
        page = gql(REPOS_Q, {"login": login, "after": after, "id": uid,
                             "aff": ["OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER"]}, token)
        conn = page["user"]["repositories"]
        repos += conn["nodes"]
        if not conn["pageInfo"]["hasNextPage"]:
            break
        after = conn["pageInfo"]["endCursor"]

    old = cache.get("repos", {})
    new_cache, commits, add, dele, stars = {}, 0, 0, 0, 0
    for r in repos:
        name = r["nameWithOwner"]
        if r["owner"]["login"].lower() == login.lower():
            stars += r["stargazerCount"]
        ref = r["defaultBranchRef"]
        n = ref["target"]["history"]["totalCount"] if ref and ref.get("target") else 0
        if n == 0:
            continue
        if name in old and old[name]["commits"] == n:
            entry = old[name]  # unchanged since last run, reuse line counts
        else:
            print(f"  counting lines in {name} ({n} commits)")
            owner, repo = name.split("/", 1)
            a = d = 0
            cur = None
            while True:
                h = gql(HISTORY_Q, {"owner": owner, "name": repo, "after": cur, "id": uid}, token)
                hist = h["repository"]["defaultBranchRef"]["target"]["history"]
                for c in hist["nodes"]:
                    a += c["additions"]
                    d += c["deletions"]
                if not hist["pageInfo"]["hasNextPage"]:
                    break
                cur = hist["pageInfo"]["endCursor"]
            entry = {"commits": n, "add": a, "del": d}
        new_cache[name] = entry
        commits += entry["commits"]
        add += entry["add"]
        dele += entry["del"]

    totals = {
        "repos": u["owned"]["totalCount"],
        "contributed": u["all"]["totalCount"],
        "stars": stars,
        "followers": u["followers"]["totalCount"],
        "commits": commits,
        "loc_add": add,
        "loc_del": dele,
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    return {"repos": new_cache, "totals": totals}


# ---------------------------------------------------------------- layout

def uptime(birthday):
    b = dt.date.fromisoformat(birthday)
    t = dt.date.today()
    y, m, d = t.year - b.year, t.month - b.month, t.day - b.day
    if d < 0:
        m -= 1
        prev = (t.replace(day=1) - dt.timedelta(days=1))
        d += prev.day
    if m < 0:
        y -= 1
        m += 12
    s = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"
    return f"{s(y, 'year')}, {s(m, 'month')}, {s(d, 'day')}"


def key_parts(key):
    """'Languages.Real' -> orange 'Languages', plain '.', orange 'Real'."""
    out = []
    for i, part in enumerate(key.split(".")):
        if i:
            out.append((".", "text"))
        out.append((part, "key"))
    return out


def row(key, value_parts, width, prefix=". "):
    """`. Key: ....... value` padded with dots to exactly `width` characters."""
    head = [(prefix, "cc")] + key_parts(key) + [(": ", "text")]
    used = sum(len(t) for t, _ in head) + sum(len(t) for t, _ in value_parts)
    dots = max(width - used - 1, 1)
    return head + [("." * dots + " ", "cc")] + value_parts


def fmt(n):
    return f"{n:,}" if isinstance(n, int) else str(n)


def stats_lines(t, width):
    left_w = width // 2 + 6
    right_w = width - left_w - 3
    l1 = row("Repos", [(fmt(t["repos"]), "value"), (" {", "text"), ("Contributed", "key"),
                       (": ", "text"), (fmt(t["contributed"]), "value"), ("}", "text")], left_w)
    r1 = row("Stars", [(fmt(t["stars"]), "value")], right_w, prefix="")
    l2 = row("Commits", [(fmt(t["commits"]), "value")], left_w)
    r2 = row("Followers", [(fmt(t["followers"]), "value")], right_w, prefix="")
    net = t["loc_add"] - t["loc_del"] if isinstance(t["loc_add"], int) else "—"
    l3 = row("Lines of Code on GitHub",
             [(fmt(net), "value"), (" ( ", "text"), (fmt(t["loc_add"]) + "++", "add"),
              (", ", "text"), (fmt(t["loc_del"]) + "--", "dele"), (" )", "text")], width)
    bar = [(" | ", "text")]
    return [l1 + bar + r1, l2 + bar + r2, l3]


def build_lines(cfg, totals):
    w = cfg.get("width", 60)
    title = cfg["title"]
    lines = [[(title, "text"), (" " + "—" * max(w - len(title) - 1, 3), "text")]]
    for item in cfg["card"]:
        if item == "":
            lines.append([(". ", "cc")])
        elif isinstance(item, str) and item.startswith("#"):
            name = item.lstrip("# ")
            lines.append([("— " + name + " ", "text"), ("—" * max(w - len(name) - 3, 3), "text")])
        elif item == "@stats":
            lines += stats_lines(totals, w)
        else:
            key, value = item
            value = value.replace("{uptime}", uptime(cfg["birthday"]))
            lines.append(row(key, [(value, "value")], w))
    for ln in lines:
        n = sum(len(t) for t, _ in ln)
        if n > w + 1:
            print(f"  warning: line is {n} chars (width {w}): {''.join(t for t, _ in ln)!r}")
    return lines


def load_art(cfg):
    """Read the ASCII art, blank out its background and trim empty edges.

    Only background characters connected to the outside edge are removed
    (a flood fill), so the same character inside the drawing is kept.
    """
    art = cfg.get("art", {})
    rows = (ROOT / art.get("file", "ascii.txt")).read_text().replace("\r", "").rstrip("\n").split("\n")
    w = max(len(r) for r in rows)
    grid = [list(r.ljust(w)) for r in rows]
    bg = art.get("background", "")
    if bg:
        h = len(grid)
        stack = [(y, x) for y in range(h) for x in (0, w - 1)] + [(y, x) for x in range(w) for y in (0, h - 1)]
        while stack:
            y, x = stack.pop()
            if 0 <= y < h and 0 <= x < w and grid[y][x] in bg:
                grid[y][x] = " "
                stack += [(y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)]
    rows = ["".join(r).rstrip() for r in grid]
    while rows and not rows[0].strip():
        rows.pop(0)
    while rows and not rows[-1].strip():
        rows.pop()
    indent = min((len(r) - len(r.lstrip()) for r in rows if r.strip()), default=0)
    return [r[indent:] for r in rows]


def render(theme, ascii_rows, lines, width):
    c = THEMES[theme]
    art_cols = max((len(r) for r in ascii_rows), default=0)
    info_h = (len(lines) - 1) * LINE_H
    # The art is drawn at whatever font size makes it exactly as tall as the info column.
    art_lh = info_h / max(len(ascii_rows) - 1, 1)
    art_lh = min(art_lh, LINE_H)
    art_fs = art_lh * 1.0
    art_w = art_cols * art_fs * (CHAR_W / FONT_SIZE)
    art_top = PAD_Y + (info_h - (len(ascii_rows) - 1) * art_lh) / 2 - (LINE_H - art_lh) * 0.3
    info_x = PAD_X + art_w + GAP * CHAR_W
    W = int(info_x + (width + 1) * CHAR_W + PAD_X)
    H = int(PAD_Y * 2 + info_h + 6)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" font-family="Consolas, Menlo, \'DejaVu Sans Mono\', \'Courier New\', monospace" '
        f'width="{W}px" height="{H}px" font-size="{FONT_SIZE}px">',
        "<style>",
        f".key {{fill: {c['key']};}} .value {{fill: {c['value']};}} .cc {{fill: {c['cc']};}} "
        f".add {{fill: {c['add']};}} .dele {{fill: {c['dele']};}} .text {{fill: {c['text']};}} "
        "text, tspan {white-space: pre;}",
        "</style>",
        f'<rect width="{W}px" height="{H}px" fill="{c["bg"]}" rx="15"/>',
        f'<text x="{PAD_X}" y="{art_top:.1f}" fill="{c["ascii"]}" font-size="{art_fs:.2f}px" xml:space="preserve">',
    ]
    for i, r in enumerate(ascii_rows):
        out.append(f'<tspan x="{PAD_X}" y="{art_top + i * art_lh:.1f}">{escape(r)}</tspan>')
    out.append("</text>")
    out.append(f'<text x="{info_x:.0f}" y="{PAD_Y}" fill="{c["text"]}" xml:space="preserve">')
    for i, ln in enumerate(lines):
        spans = "".join(f'<tspan class="{cls}">{escape(t)}</tspan>' for t, cls in ln)
        out.append(f'<tspan x="{info_x:.0f}" y="{PAD_Y + i * LINE_H}">{spans}</tspan>')
    out.append("</text>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main():
    cfg = json.loads((ROOT / "profile.json").read_text())
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    offline = "--offline" in sys.argv or not token

    if offline:
        if not token and "--offline" not in sys.argv:
            print("No GH_TOKEN set, using the last saved stats.")
    elif cfg["username"] == "your-github-username":
        print("Set \"username\" in profile.json to fetch stats. Using saved stats.")
    else:
        cache = fetch_stats(cfg["username"], token, cache)
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True))

    totals = cache.get("totals") or {k: "—" for k in
                                     ["repos", "contributed", "stars", "followers", "commits", "loc_add", "loc_del"]}
    ascii_rows = load_art(cfg)
    lines = build_lines(cfg, totals)
    for theme in THEMES:
        (ROOT / f"{theme}_mode.svg").write_text(render(theme, ascii_rows, lines, cfg.get("width", 60)))
    print("Wrote dark_mode.svg and light_mode.svg")


if __name__ == "__main__":
    main()

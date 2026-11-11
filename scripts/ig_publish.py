#!/usr/bin/env python3
"""Publish due PİKSEL carousels from queue/*.json to Instagram via the Graph API.

Queue item: {"id","publish_at" (ISO, Asia/Baku),"caption","images":[3 https URLs],"status":"pending"}
On success: status="published", ig_media_id, published_at. On failure: status="error", error.
At most MAX_PER_RUN posts per run, oldest first. The token is read from IG_ACCESS_TOKEN and is
never printed. DRY_RUN=1 creates the containers and waits for FINISHED but does not publish and
does not change the queue. ONLY_ID=<id> limits the run to one queue item (ignores publish_at).
"""
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BAKU = ZoneInfo("Asia/Baku")
VER = os.environ.get("GRAPH_VERSION") or "v27.0"
TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
MAX_PER_RUN = int(os.environ.get("MAX_PER_RUN") or 1)
DRY = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
ONLY = os.environ.get("ONLY_ID", "").strip()
DEFAULT_IG_USER_ID = "17841425341415868"  # @pixelpressaz (shown in the Meta app, 2026-11-11)
KEEP_DAYS = 3  # published ig/<date>/ images older than this are removed from the tree


def scrub(s):
    s = str(s)
    if TOKEN:
        s = s.replace(TOKEN, "***")
    return re.sub(r"access_token=[^&\s\"']+", "access_token=***", s)


def call(method, url, params=None):
    params = dict(params or {})
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        req = urllib.request.Request(url + "?" + data.decode())
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            err = json.loads(body).get("error", {})
            msg = f"HTTP {e.code}: {err.get('message')} (type={err.get('type')}, code={err.get('code')}, sub={err.get('error_subcode')})"
        except Exception:
            msg = f"HTTP {e.code}: {body[:300]}"
        raise RuntimeError(scrub(msg)) from None
    except urllib.error.URLError as e:
        raise RuntimeError(scrub(f"network error: {e.reason}")) from None


def find_user():
    """Return (base_url, ig_user_id)."""
    uid = os.environ.get("IG_USER_ID", "").strip() or DEFAULT_IG_USER_ID
    fb = f"https://graph.facebook.com/{VER}"
    if uid:
        me = call("GET", f"{fb}/{uid}", {"fields": "id,username"})
        print(f"IG user: @{me.get('username')} {me.get('id')}")
        return fb, uid
    errs = []
    try:
        pages = call("GET", f"{fb}/me/accounts", {"fields": "name,instagram_business_account"})
        for p in pages.get("data", []):
            iba = p.get("instagram_business_account")
            if iba and iba.get("id"):
                print(f"IG user found via Facebook page '{p.get('name')}': {iba['id']}")
                return fb, iba["id"]
        errs.append("/me/accounts returned no page with instagram_business_account")
    except RuntimeError as e:
        errs.append(f"/me/accounts: {e}")
    # System-user token (Unified login / business portfolio): look through the token's businesses
    try:
        biz = call("GET", f"{fb}/me/businesses", {"fields": "id,name"})
        for b in biz.get("data", []):
            for edge in ("owned_instagram_accounts", "instagram_business_accounts", "instagram_accounts"):
                try:
                    r = call("GET", f"{fb}/{b['id']}/{edge}", {"fields": "id,username"})
                except RuntimeError as e:
                    errs.append(f"{edge}: {e}")
                    continue
                for a in r.get("data", []):
                    if a.get("id"):
                        print(f"IG user found via business '{b.get('name')}' ({edge}): @{a.get('username')} {a['id']}")
                        return fb, a["id"]
        errs.append("/me/businesses: no Instagram account found")
    except RuntimeError as e:
        errs.append(f"/me/businesses: {e}")
    # Fallback: token from "Instagram API with Instagram Login"
    ig = f"https://graph.instagram.com/{VER}"
    try:
        me = call("GET", f"{ig}/me", {"fields": "user_id,username"})
        if me.get("user_id"):
            print(f"IG user found via Instagram Login: @{me.get('username')} {me['user_id']}")
            return ig, str(me["user_id"])
    except RuntimeError as e:
        errs.append(f"graph.instagram.com/me: {e}")
    raise RuntimeError("could not find the Instagram user id; " + " | ".join(errs))


def wait_finished(base, cid, limit=180):
    t0 = time.time()
    while True:
        st = call("GET", f"{base}/{cid}", {"fields": "status_code,status"})
        code = st.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"container {cid} {code}: {st.get('status')}")
        if time.time() - t0 > limit:
            raise RuntimeError(f"container {cid} not FINISHED after {limit}s (last {code})")
        time.sleep(5)


def publish(base, uid, item):
    children = []
    for url in item["images"]:
        c = call("POST", f"{base}/{uid}/media", {"image_url": url, "is_carousel_item": "true"})
        children.append(c["id"])
    for cid in children:
        wait_finished(base, cid)
    car = call("POST", f"{base}/{uid}/media",
               {"media_type": "CAROUSEL", "children": ",".join(children), "caption": item["caption"]})
    wait_finished(base, car["id"])
    if DRY:
        print(f"  DRY_RUN: carousel container {car['id']} FINISHED, not published")
        return None
    res = call("POST", f"{base}/{uid}/media_publish", {"creation_id": car["id"]})
    return res["id"]


def key(caption):
    """First line of a caption, normalized, to spot posts already on the account."""
    line = (caption or "").strip().split("\n", 1)[0]
    return re.sub(r"\W+", "", line.lower())[:50]


def existing_keys(base, uid):
    keys, url, params = set(), f"{base}/{uid}/media", {"fields": "caption,timestamp", "limit": "100"}
    for _ in range(3):  # last ~300 posts
        r = call("GET", url, params)
        for m in r.get("data", []):
            k = key(m.get("caption"))
            if k:
                keys.add(k)
        nxt = r.get("paging", {}).get("next")
        if not nxt:
            break
        u = urllib.parse.urlparse(nxt)
        url = f"{u.scheme}://{u.netloc}{u.path}"
        params = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items() if k != "access_token"}
    return keys


def parse_t(s):
    t = datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=BAKU)


def cleanup(now):
    """Remove images of posts published more than KEEP_DAYS ago (Pages size limit)."""
    removed = 0
    for qf in glob.glob("queue/*.json"):
        for it in json.load(open(qf, encoding="utf-8")):
            if it.get("status") != "published" or not it.get("published_at"):
                continue
            if now - parse_t(it["published_at"]) < timedelta(days=KEEP_DAYS):
                continue
            for u in it.get("images", []):
                p = u.split(".github.io/", 1)[-1]
                if p.startswith("ig/") and os.path.exists(p):
                    os.remove(p)
                    removed += 1
    if removed:
        print(f"cleanup: removed {removed} old published images")


def main():
    now = datetime.now(BAKU)
    due = []  # (publish_at, file, index)
    queues = {}
    for qf in sorted(glob.glob("queue/*.json")):
        items = json.load(open(qf, encoding="utf-8"))
        queues[qf] = items
        for i, it in enumerate(items):
            if ONLY:
                if it.get("id") == ONLY:
                    due.append((parse_t(it["publish_at"]), qf, i))
            elif it.get("status") == "pending" and parse_t(it["publish_at"]) <= now:
                due.append((parse_t(it["publish_at"]), qf, i))
    due.sort()
    print(f"{now.isoformat(timespec='minutes')} Baku: {len(due)} post(s) due, Graph {VER}, dry_run={DRY}")
    if not due:
        if not DRY:
            cleanup(now)
        return 0
    if not TOKEN:
        print("ERROR: secret IG_ACCESS_TOKEN is not set; due posts stay pending")
        return 1
    try:
        base, uid = find_user()
    except RuntimeError as e:
        print(f"ERROR: {scrub(e)}")
        return 1
    try:
        seen = existing_keys(base, uid)
        print(f"{len(seen)} existing posts checked for duplicates")
    except RuntimeError as e:
        print(f"ERROR reading existing posts, stopping to avoid duplicates: {scrub(e)}")
        return 1
    changed = set()
    fails = 0
    done = 0
    for _, qf, i in due:
        if done >= MAX_PER_RUN:
            break
        it = queues[qf][i]
        print(f"- {it['id']} (publish_at {it['publish_at']})")
        if key(it["caption"]) in seen and not ONLY:
            print("  already on Instagram, skipped")
            if not DRY:
                it.update(status="skipped_duplicate")
                changed.add(qf)
            continue
        done += 1
        try:
            mid = publish(base, uid, it)
            if mid:
                seen.add(key(it["caption"]))
                it.update(status="published", ig_media_id=mid,
                          published_at=datetime.now(BAKU).isoformat(timespec="seconds"))
                it.pop("error", None)
                changed.add(qf)
                print(f"  published: {mid}")
        except Exception as e:
            fails += 1
            msg = scrub(e)
            print(f"  ERROR: {msg}")
            if not DRY:
                it.update(status="error", error=msg[:500])
                changed.add(qf)
    if not DRY:
        for qf in changed:
            with open(qf, "w", encoding="utf-8") as f:
                json.dump(queues[qf], f, ensure_ascii=False, indent=1)
                f.write("\n")
        cleanup(now)
    return 1 if DRY and fails else 0


if __name__ == "__main__":
    sys.exit(main())

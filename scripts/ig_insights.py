#!/usr/bin/env python3
"""Read-only Instagram insights report for @pixelpressaz.

Prints an aggregated report (account totals + per-post metrics + hour/topic breakdown) to the job
log and $GITHUB_STEP_SUMMARY. Changes nothing on Instagram and nothing in the repo. Token is never printed.
"""
import collections
import glob
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(__file__))
from ig_publish import call, find_user  # noqa: E402

BAKU = ZoneInfo("Asia/Baku")
out = []


def p(s=""):
    print(s)
    out.append(s)


def try_call(url, params):
    try:
        return call("GET", url, params), None
    except RuntimeError as e:
        return None, str(e)


def main():
    base, uid = find_user()
    me, err = try_call(f"{base}/{uid}", {"fields": "username,followers_count,follows_count,media_count"})
    p("## Hesab")
    p(json.dumps(me or {"error": err}, ensure_ascii=False))

    # Account-level daily totals over the last 28 days (API limit is 30)
    until = int(datetime.now(timezone.utc).timestamp())
    since = until - 28 * 86400
    p("\n## Hesab üzrə 28 gün (total_value)")
    for m in ["reach", "views", "accounts_engaged", "total_interactions", "profile_views",
              "follows_and_unfollows", "website_clicks", "likes", "comments", "saves", "shares"]:
        r, e = try_call(f"{base}/{uid}/insights", {"metric": m, "period": "day", "metric_type": "total_value",
                                                   "since": since, "until": until})
        if r:
            v = [d.get("total_value", {}) for d in r.get("data", [])]
            p(f"- {m}: {json.dumps(v, ensure_ascii=False)}")
        else:
            p(f"- {m}: XƏTA {e}")
    # Daily reach series (time_series)
    r, e = try_call(f"{base}/{uid}/insights", {"metric": "reach", "period": "day", "since": since, "until": until})
    if r and r.get("data"):
        p("\n## Günlük reach")
        for v in r["data"][0].get("values", []):
            p(f"- {v.get('end_time','')[:10]}: {v.get('value')}")
    for m, br in [("follower_demographics", "city"), ("follower_demographics", "age"), ("follower_demographics", "gender"),
                  ("engaged_audience_demographics", "city")]:
        r, e = try_call(f"{base}/{uid}/insights", {"metric": m, "period": "lifetime", "metric_type": "total_value",
                                                   "timeframe": "this_month", "breakdown": br})
        p(f"\n## {m} / {br}")
        p(json.dumps(r["data"][0].get("total_value", {}) if r and r.get("data") else {"error": e}, ensure_ascii=False)[:1500])
    r, e = try_call(f"{base}/{uid}/insights", {"metric": "online_followers", "period": "lifetime"})
    p("\n## online_followers")
    p(json.dumps(r.get("data", []) if r else {"error": e}, ensure_ascii=False)[:2500])

    # Per-post metrics for posts we published
    posts = []
    for qf in sorted(glob.glob("queue/2*.json")):
        for it in json.load(open(qf, encoding="utf-8")):
            if it.get("status") == "published" and it.get("ig_media_id"):
                posts.append(it)
    rows, errs = [], collections.Counter()
    metrics = "reach,views,likes,comments,saved,shares,total_interactions"
    for it in posts:
        r, e = try_call(f"{base}/{it['ig_media_id']}/insights", {"metric": metrics})
        if not r:
            r, e2 = try_call(f"{base}/{it['ig_media_id']}/insights", {"metric": "reach,likes,comments,saved,shares"})
            if not r:
                errs[(e or "")[:160]] += 1
                continue
        vals = {d["name"]: (d.get("values") or [{}])[0].get("value", d.get("total_value", {}).get("value", 0)) for d in r.get("data", [])}
        cap = it["caption"]
        tags = re.findall(r"#\S+", cap)
        t = datetime.fromisoformat(it.get("published_at") or it["publish_at"]).astimezone(BAKU)
        rows.append({"id": it["id"], "hour": t.hour, "wd": t.strftime("%a"), "title": cap.split("\n")[0][:70],
                     "topic": "/".join(x for x in tags if x not in ("#piksel",))[:60], "len": len(cap), **vals})
        time.sleep(0.15)
    p(f"\n## Postlar: {len(rows)} oxundu, {sum(errs.values())} xəta")
    for k, n in errs.most_common(3):
        p(f"- {n}× {k}")
    if not rows:
        return 1
    key = "views" if any(r.get("views") for r in rows) else "reach"

    def agg(group):
        g = collections.defaultdict(list)
        for r in rows:
            g[group(r)].append(r)
        res = []
        for k, rs in g.items():
            n = len(rs)
            res.append((k, n, sum(r.get(key, 0) for r in rs) / n, sum(r.get("reach", 0) for r in rs) / n,
                        sum(r.get("saved", 0) + r.get("shares", 0) for r in rs) / n,
                        sum(r.get("total_interactions", r.get("likes", 0)) for r in rs) / n))
        return sorted(res, key=lambda x: -x[2])

    tot = {m: sum(r.get(m, 0) for r in rows) for m in ["reach", "views", "likes", "comments", "saved", "shares"]}
    p(f"Cəmi: {json.dumps(tot)} | post başına {key}: {tot[key]/len(rows):.1f}")
    for name, fn in [("Saat (Bakı)", lambda r: r["hour"]), ("Həftə günü", lambda r: r["wd"]),
                     ("Gün", lambda r: r["id"][:10]),
                     ("Bölmə", lambda r: ("az" if "#azərbaycan" in r["topic"] else "dünya" if "#dünya" in r["topic"] else "?")),
                     ("Mövzu", lambda r: next((t for t in ["#iqtisadiyyat", "#texnologiya", "#idman", "#sosial", "#elm", "#süniintellekt", "#futbol", "#birja"] if t in r["topic"]), "digər"))]:
        p(f"\n### {name}: açar, say, ort. {key}, ort. reach, ort. save+share, ort. interaction")
        for k, n, a, rc, ss, ti in agg(fn):
            p(f"- {k}: {n} | {a:.1f} | {rc:.1f} | {ss:.2f} | {ti:.2f}")
    rows.sort(key=lambda r: -r.get(key, 0))
    for label, sel in [("TOP 15", rows[:15]), ("ƏN ZƏİF 10", rows[-10:])]:
        p(f"\n### {label} ({key})")
        for r in sel:
            p(f"- {r['id']} {r['hour']:02d}h {key}={r.get(key,0)} reach={r.get('reach',0)} like={r.get('likes',0)} "
              f"save={r.get('saved',0)} share={r.get('shares',0)} | {r['title']}")
    p("\n### JSON")
    p(json.dumps(rows, ensure_ascii=False))
    s = os.environ.get("GITHUB_STEP_SUMMARY")
    if s:
        with open(s, "a", encoding="utf-8") as f:
            f.write("\n".join(out[:-1]) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

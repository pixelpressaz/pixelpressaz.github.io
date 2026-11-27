#!/usr/bin/env python3
"""Build static SEO pages for PixelPress AZ from posts.json.

Generates (all derived, safe to delete and rebuild):
  xeber/<id>/index.html     one page per news item (title, description, OG, NewsArticle JSON-LD)
  xeber/index.html          archive: every day with its news
  gun/<date>/index.html     one page per day
  movzu/<slug>/index.html   one page per topic (latest items)
  sitemap.xml, robots.txt, feed.xml (RSS), logo.png
and refreshes the marked SEO block in index.html (canonical, OG image, static latest links).

Site URL: CNAME file if present (custom domain), else SITE_URL env, else https://pixelpressaz.github.io
Optional site-config.json: {"google_site_verification": "...", "bing_site_verification": "..."}
"""
import html
import json
import os
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from email.utils import format_datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

NAME = "PixelPress AZ"
TZ = "+04:00"
MON = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avqust",
       "sentyabr", "oktyabr", "noyabr", "dekabr"]
REGION_LABEL = {"Azərbaycan": "Azərbaycan xəbərləri", "Dünya": "Dünya xəbərləri"}


def site_url():
    if os.path.exists("CNAME"):
        host = open("CNAME").read().strip().split()[0]
        if host:
            return "https://" + host.rstrip("/")
    return os.environ.get("SITE_URL", "https://pixelpressaz.github.io").rstrip("/")


BASE = site_url()
CONF = json.load(open("site-config.json")) if os.path.exists("site-config.json") else {}

E = lambda s: html.escape(str(s), quote=True)


def plain(s):
    """Drop emoji / pictographs, collapse spaces."""
    out = []
    for ch in str(s):
        cat = unicodedata.category(ch)
        if cat in ("So", "Sk", "Cs", "Co") or ch in "‍️":
            continue
        out.append(ch)
    return re.sub(r"\s+", " ", "".join(out)).strip(" –-")


def cut(s, n):
    s = plain(s)
    if len(s) <= n:
        return s
    s = s[: n - 1].rsplit(" ", 1)[0].rstrip(",;:–- ")
    return s + "…"


TR = str.maketrans({"ə": "e", "Ə": "e", "ı": "i", "İ": "i", "ö": "o", "Ö": "o", "ü": "u", "Ü": "u",
                    "ğ": "g", "Ğ": "g", "ş": "s", "Ş": "s", "ç": "c", "Ç": "c"})


def slugify(s):
    s = plain(s).translate(TR).lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def human_date(d):
    y, m, dd = d.split("-")
    return f"{int(dd)} {MON[int(m) - 1]} {y}"


def iso(p):
    t = p.get("time") or "09:00"
    return f"{p['date']}T{t}:00{TZ}"


def url_post(p):
    return f"{BASE}/xeber/{p['id']}/"


def article_body(p):
    """Body without the trailing engagement question (ends with 👇)."""
    body = [b for b in p.get("body", []) if b]
    if len(body) > 1 and "👇" in body[-1]:
        return body[:-1], body[-1]
    return body, None


def description(p):
    body, _ = article_body(p)
    return cut(" ".join(body) or p["title"], 158)


CSS = """:root{--bg:#f4f6fb;--card:#fff;--ink:#0b1220;--muted:#5b6475;--line:#e3e7ef;--brand:#1e5bff;--chip:#eef2ff}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0a0d14;--card:#121722;--ink:#eef1f7;--muted:#9aa3b5;--line:#232a38;--chip:#1a2340}}
:root[data-theme="dark"]{--bg:#0a0d14;--card:#121722;--ink:#eef1f7;--muted:#9aa3b5;--line:#232a38;--chip:#1a2340}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--ink);font-family:Montserrat,system-ui,-apple-system,Segoe UI,Arial,sans-serif}
a{color:inherit}.wrap{max-width:1040px;margin:0 auto;padding:0 16px}
header{border-bottom:1px solid var(--line);background:var(--bg)}.bar{display:flex;align-items:center;gap:14px;min-height:60px;flex-wrap:wrap;padding:8px 0}
.logo{display:flex;align-items:center;gap:10px;font-weight:900;font-size:19px;text-decoration:none}.logo i{width:32px;height:32px;background:var(--brand);display:grid;place-items:center;color:#fff;font-style:normal}.logo b{color:var(--brand)}
.bar nav{display:flex;gap:4px;flex-wrap:wrap}.bar nav a{text-decoration:none;color:var(--muted);font-weight:600;font-size:14px;padding:6px 10px;border-radius:999px}.bar nav a:hover{color:var(--ink)}
.ig{margin-left:auto;font-weight:700;font-size:13px;text-decoration:none;background:var(--brand);color:#fff;padding:9px 14px;border-radius:999px}
.crumbs{font-size:13px;color:var(--muted);margin:18px 0 8px}.crumbs a{text-decoration:none}.crumbs a:hover{text-decoration:underline}
.tags{display:flex;gap:8px;align-items:center;font-size:12px;font-weight:700;color:var(--muted);flex-wrap:wrap}.chip{background:var(--chip);color:var(--brand);padding:3px 8px;border-radius:6px;text-decoration:none}
.post{display:grid;grid-template-columns:minmax(0,420px) 1fr;gap:28px;align-items:start;margin:8px 0 32px}
.slides{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;border-radius:14px;background:#000;aspect-ratio:4/5;scrollbar-width:thin}
.slides div{flex:none;width:100%;height:100%;overflow:hidden;position:relative;scroll-snap-align:start}
.slides img{position:absolute;top:0;height:100%;width:300%;max-width:none}
.hint{font-size:12px;color:var(--muted);margin-top:6px;text-align:center}
h1{font-size:30px;line-height:1.2;font-weight:900;margin:10px 0 14px}
.post p{line-height:1.75;font-size:16px;margin:0 0 14px}.q{color:var(--muted)}
.src{font-size:13px;color:var(--muted);border-top:1px solid var(--line);padding-top:12px;margin-top:6px;display:flex;flex-direction:column;gap:6px}
h2{font-size:20px;font-weight:800;margin:28px 0 14px}
.list{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px;padding-bottom:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;text-decoration:none;display:flex;flex-direction:column}
.card .th{aspect-ratio:4/5;overflow:hidden;position:relative;background:#000}.card .th img{position:absolute;top:0;left:0;height:100%;width:300%;max-width:none}
.card .m{padding:10px 12px 12px;display:flex;flex-direction:column;gap:6px}.card h3{margin:0;font-size:14px;line-height:1.35}
.days{display:flex;flex-direction:column;gap:22px;padding-bottom:30px}.days h2{margin:0 0 8px;font-size:17px}.days ul{margin:0;padding-left:18px;line-height:1.7}
.pn{display:flex;justify-content:space-between;gap:12px;margin:10px 0 0;font-size:14px}.pn a{text-decoration:none;color:var(--brand);font-weight:600}
footer{border-top:1px solid var(--line);color:var(--muted);font-size:13px;padding:24px 0 40px;margin-top:20px}footer a{margin-right:12px}
@media (max-width:760px){.post{grid-template-columns:1fr}h1{font-size:23px}.list{grid-template-columns:repeat(2,1fr);gap:10px}.card h3{font-size:13px}}
"""

FONT = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@500;600;700;800;900&display=swap" rel="stylesheet">')
ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' "
        "fill='%231e5bff'/%3E%3Ctext x='16' y='23' font-family='Arial' font-weight='900' font-size='20' fill='white' "
        "text-anchor='middle'%3EP%3C/text%3E%3C/svg%3E")


def verification_meta():
    out = ""
    if CONF.get("google_site_verification"):
        out += f'<meta name="google-site-verification" content="{E(CONF["google_site_verification"])}">\n'
    if CONF.get("bing_site_verification"):
        out += f'<meta name="msvalidate.01" content="{E(CONF["bing_site_verification"])}">\n'
    return out


def head(title, desc, canonical, image=None, og_type="website", extra=""):
    img = image or f"{BASE}/logo.png"
    return f"""<!doctype html>
<html lang="az">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{E(canonical)}">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta property="og:site_name" content="{NAME}">
<meta property="og:locale" content="az_AZ">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{E(title)}">
<meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{E(canonical)}">
<meta property="og:image" content="{E(img)}">
<meta name="twitter:card" content="summary_large_image">
<link rel="alternate" type="application/rss+xml" title="{NAME}" href="{BASE}/feed.xml">
<link rel="icon" href="{ICON}">
{verification_meta()}{FONT}
<link rel="stylesheet" href="{BASE}/assets/site.css">
{extra}</head>
<body>
<header><div class="wrap bar">
<a class="logo" href="{BASE}/"><i>P</i><span>PixelPress<b>AZ</b></span></a>
<nav><a href="{BASE}/">Son xəbərlər</a>{''.join(f'<a href="{BASE}/movzu/{slugify(t)}/">{E(t)}</a>' for t in TOPICS)}<a href="{BASE}/xeber/">Arxiv</a></nav>
<a class="ig" href="https://instagram.com/pixelpressaz" rel="noopener">@pixelpressaz</a>
</div></header>
<main class="wrap">
"""


FOOT = """</main>
<footer><div class="wrap"><p>{name} · Azərbaycan və dünyadan qısa, aydın xəbərlər · Mənbələr hər xəbərin altında göstərilir · Fotolar açıq lisenziyalı (Wikimedia Commons)</p>
<p><a href="{base}/">Ana səhifə</a><a href="{base}/xeber/">Xəbər arxivi</a><a href="{base}/feed.xml">RSS</a><a href="https://instagram.com/pixelpressaz" rel="noopener">Instagram</a></p></div></footer>
</body>
</html>
"""


def foot():
    return FOOT.format(name=NAME, base=BASE)


def card(p):
    return (f'<a class="card" href="{url_post(p)}"><div class="th"><img src="{BASE}/{p["id"]}.jpg" alt="{E(plain(p["title"]))}" '
            f'loading="lazy" width="1620" height="675"></div><div class="m"><div class="tags"><span class="chip">{E(p["region"])}</span>'
            f'{E(p["topic"])} · {human_date(p["date"])}</div><h3>{E(plain(p["title"]))}</h3></div></a>')


def jsonld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False).replace("</", "<\\/") + "</script>\n"


PUBLISHER = {"@type": "NewsMediaOrganization", "name": NAME, "url": BASE + "/",
             "logo": {"@type": "ImageObject", "url": BASE + "/logo.png", "width": 512, "height": 512},
             "sameAs": ["https://www.instagram.com/pixelpressaz/"]}


def page_post(p, prev, nxt, related):
    t = plain(p["title"])
    title = t + " | " + NAME if len(t) <= 52 else cut(t, 68)
    desc = description(p)
    canon = url_post(p)
    img = f"{BASE}/{p['id']}.jpg"
    body, question = article_body(p)
    ld = {
        "@context": "https://schema.org", "@type": "NewsArticle",
        "headline": cut(t, 110), "description": desc,
        "image": [img], "datePublished": iso(p), "dateModified": iso(p),
        "inLanguage": "az", "articleSection": p["topic"],
        "keywords": ", ".join([p["region"], p["topic"]]),
        "mainEntityOfPage": {"@type": "WebPage", "@id": canon},
        "author": {"@type": "Organization", "name": NAME, "url": BASE + "/"},
        "publisher": PUBLISHER,
        "articleBody": " ".join(plain(b) for b in body),
    }
    crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": NAME, "item": BASE + "/"},
        {"@type": "ListItem", "position": 2, "name": p["topic"], "item": f"{BASE}/movzu/{slugify(p['topic'])}/"},
        {"@type": "ListItem", "position": 3, "name": cut(t, 80)}]}
    extra = (f'<meta property="article:published_time" content="{iso(p)}">\n'
             f'<meta property="article:section" content="{E(p["topic"])}">\n' + jsonld(ld) + jsonld(crumbs))
    s = head(title, desc, canon, img, "article", extra)
    s += (f'<div class="crumbs"><a href="{BASE}/">Ana səhifə</a> › <a href="{BASE}/movzu/{slugify(p["topic"])}/">{E(p["topic"])}</a> › '
          f'<a href="{BASE}/gun/{p["date"]}/">{human_date(p["date"])}</a></div>\n<article class="post">\n<div>'
          f'<div class="slides">' +
          "".join(f'<div><img src="{img}" alt="{E(t) if i == 0 else ""}" width="1620" height="675" style="left:-{i * 100}%"'
                  f'{"" if i == 0 else " loading=\"lazy\""}></div>' for i in range(3)) +
          '</div><div class="hint">Şəkilləri sürüşdürün →</div></div>\n<div>'
          f'<div class="tags"><a class="chip" href="{BASE}/movzu/{slugify(p["topic"])}/">{E(p["topic"])}</a>{E(p["region"])} · '
          f'<time datetime="{iso(p)}">{human_date(p["date"])}, {E(p.get("time", ""))}</time></div>\n'
          f'<h1>{E(t)}</h1>\n' + "".join(f"<p>{E(b)}</p>\n" for b in body) +
          (f'<p class="q">{E(question)}</p>\n' if question else "") +
          f'<div class="src"><span>Mənbə: {E(p.get("src", ""))}</span><span>Fotolar: {E(p.get("credits", ""))}</span>'
          f'<span>Bu xəbəri Instagram-da da izləyin: <a href="https://instagram.com/pixelpressaz" rel="noopener">@pixelpressaz</a></span></div>\n'
          '<div class="pn">' +
          (f'<a href="{url_post(prev)}" rel="prev">← {E(cut(prev["title"], 60))}</a>' if prev else "<span></span>") +
          (f'<a href="{url_post(nxt)}" rel="next">{E(cut(nxt["title"], 60))} →</a>' if nxt else "<span></span>") +
          "</div>\n</div>\n</article>\n")
    if related:
        s += f'<h2>Digər {E(p["topic"].lower())} xəbərləri</h2>\n<div class="list">' + "".join(card(r) for r in related) + "</div>\n"
    return s + foot()


def write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def make_logo():
    if os.path.exists("logo.png"):
        return
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return
    im = Image.new("RGB", (512, 512), "#1e5bff")
    d = ImageDraw.Draw(im)
    font = None
    for f in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
        if os.path.exists(f):
            font = ImageFont.truetype(f, 340)
            break
    font = font or ImageFont.load_default()
    d.text((256, 270), "P", fill="white", font=font, anchor="mm")
    im.save("logo.png", optimize=True)


START, END = "<!--seo:start-->", "<!--seo:end-->"
LSTART, LEND = "<!--seo-latest:start-->", "<!--seo-latest:end-->"


def update_index(posts):
    """Refresh the SEO blocks in index.html without changing how the page works."""
    if not os.path.exists("index.html"):
        return
    s = open("index.html", encoding="utf-8").read()
    ld = {"@context": "https://schema.org", "@graph": [
        dict(PUBLISHER, **{"@id": BASE + "/#org"}),
        {"@type": "WebSite", "@id": BASE + "/#site", "url": BASE + "/", "name": NAME, "inLanguage": "az",
         "publisher": {"@id": BASE + "/#org"}}]}
    block = (f'{START}\n<link rel="canonical" href="{BASE}/">\n<meta property="og:url" content="{BASE}/">\n'
             f'<meta property="og:type" content="website">\n<meta property="og:site_name" content="{NAME}">\n'
             f'<meta property="og:image" content="{BASE}/{posts[0]["id"]}.jpg">\n<meta name="robots" content="index,follow,max-image-preview:large">\n'
             f'<link rel="alternate" type="application/rss+xml" title="{NAME}" href="{BASE}/feed.xml">\n'
             f'{verification_meta()}{jsonld(ld)}{END}')
    if START in s:
        s = re.sub(re.escape(START) + ".*?" + re.escape(END), lambda m: block, s, flags=re.S)
    else:
        s = s.replace("</head>", block + "\n</head>", 1)
    latest = (f'{LSTART}\n<div class="wrap" role="navigation" aria-label="Son xəbərlər" style="font-size:13px;line-height:1.8;padding-bottom:28px;color:var(--muted)">'
              f'<strong>Son xəbərlər:</strong> ' +
              " · ".join(f'<a href="xeber/{p["id"]}/">{E(cut(p["title"], 90))}</a>' for p in posts[:30]) +
              f' · <a href="xeber/"><strong>Bütün xəbərlər (arxiv)</strong></a></div>\n{LEND}')
    if LSTART in s:
        s = re.sub(re.escape(LSTART) + ".*?" + re.escape(LEND), lambda m: latest, s, flags=re.S)
    else:
        s = s.replace("</footer>", "</footer>\n" + latest, 1)
    # Link from the pop-up to the article's own page (keeps the pop-up as it is).
    hook = "<button class=\"share\" id=\"share\">Linki kopyala</button>"
    link = ("<a class=\"share\" href=\"xeber/${cur.id}/\" style=\"text-decoration:none\">Xəbərin səhifəsi →</a>")
    if hook in s and link not in s:
        s = s.replace(hook, hook + link, 1)
    open("index.html", "w", encoding="utf-8").write(s)


def main():
    global TOPICS
    posts = json.load(open("posts.json", encoding="utf-8"))
    posts = [p for p in posts if p.get("id") and p.get("title") and os.path.exists(p["id"] + ".jpg")]
    posts.sort(key=lambda p: (p["date"], p.get("time", ""), p["id"]), reverse=True)
    if not posts:
        sys.exit("no posts")
    counts = {}
    for p in posts:
        counts[p["topic"]] = counts.get(p["topic"], 0) + 1
    TOPICS = sorted(counts, key=lambda t: -counts[t])

    for d in ("xeber", "gun", "movzu"):
        shutil.rmtree(d, ignore_errors=True)
    write("assets/site.css", CSS)
    make_logo()

    by_topic = {t: [p for p in posts if p["topic"] == t] for t in TOPICS}
    for i, p in enumerate(posts):
        newer = posts[i - 1] if i > 0 else None
        older = posts[i + 1] if i + 1 < len(posts) else None
        same = by_topic[p["topic"]]
        j = same.index(p)
        related = (same[max(0, j - 3):j] + same[j + 1:j + 7])[:6]
        write(f"xeber/{p['id']}/index.html", page_post(p, older, newer, related))

    days = {}
    for p in posts:
        days.setdefault(p["date"], []).append(p)
    dlist = list(days)
    for k, d in enumerate(dlist):
        hd = human_date(d)
        s = head(f"{hd} xəbərləri: Azərbaycan və dünya | {NAME}",
                 cut(f"{hd} tarixinin əsas xəbərləri: " + "; ".join(plain(p["title"]) for p in days[d][:4]), 158),
                 f"{BASE}/gun/{d}/", f"{BASE}/{days[d][0]['id']}.jpg")
        s += (f'<div class="crumbs"><a href="{BASE}/">Ana səhifə</a> › <a href="{BASE}/xeber/">Arxiv</a></div>'
              f'<h1>{hd} xəbərləri</h1>\n<div class="list">' + "".join(card(p) for p in days[d]) + "</div>\n<div class=\"pn\">" +
              (f'<a href="{BASE}/gun/{dlist[k + 1]}/">← {human_date(dlist[k + 1])}</a>' if k + 1 < len(dlist) else "<span></span>") +
              (f'<a href="{BASE}/gun/{dlist[k - 1]}/">{human_date(dlist[k - 1])} →</a>' if k > 0 else "<span></span>") + "</div>\n")
        write(f"gun/{d}/index.html", s + foot())

    s = head(f"Xəbər arxivi | {NAME}", "PixelPress AZ-ın bütün xəbərləri tarixə görə: Azərbaycan və dünya, iqtisadiyyat, texnologiya, idman, sosial.",
             f"{BASE}/xeber/")
    s += '<h1>Xəbər arxivi</h1>\n<div class="days">' + "".join(
        f'<section><h2><a href="{BASE}/gun/{d}/">{human_date(d)}</a></h2><ul>' +
        "".join(f'<li><a href="{url_post(p)}">{E(plain(p["title"]))}</a></li>' for p in days[d]) + "</ul></section>"
        for d in dlist) + "</div>\n"
    write("xeber/index.html", s + foot())

    for t in TOPICS:
        items = by_topic[t][:60]
        s = head(f"{t} xəbərləri: Azərbaycan və dünya | {NAME}",
                 cut(f"{t} üzrə son xəbərlər: " + "; ".join(plain(p["title"]) for p in items[:3]), 158),
                 f"{BASE}/movzu/{slugify(t)}/", f"{BASE}/{items[0]['id']}.jpg")
        s += (f'<div class="crumbs"><a href="{BASE}/">Ana səhifə</a></div><h1>{E(t)} xəbərləri</h1>\n<div class="list">' +
              "".join(card(p) for p in items) + f'</div>\n<p><a href="{BASE}/xeber/">Bütün xəbərlər arxivdə →</a></p>\n')
        write(f"movzu/{slugify(t)}/index.html", s + foot())

    # sitemap
    urls = [(BASE + "/", posts[0]["date"], "hourly", "1.0"), (BASE + "/xeber/", posts[0]["date"], "daily", "0.6")]
    urls += [(f"{BASE}/movzu/{slugify(t)}/", by_topic[t][0]["date"], "daily", "0.6") for t in TOPICS]
    urls += [(f"{BASE}/gun/{d}/", d, "weekly", "0.4") for d in dlist]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">']
    for u, lm, cf, pr in urls:
        sm.append(f"<url><loc>{E(u)}</loc><lastmod>{lm}</lastmod><changefreq>{cf}</changefreq><priority>{pr}</priority></url>")
    for p in posts:
        sm.append(f"<url><loc>{url_post(p)}</loc><lastmod>{iso(p)}</lastmod><image:image><image:loc>{BASE}/{p['id']}.jpg</image:loc></image:image></url>")
    sm.append("</urlset>")
    write("sitemap.xml", "\n".join(sm) + "\n")

    write("robots.txt", f"User-agent: *\nAllow: /\nDisallow: /queue/\nDisallow: /scripts/\n\nSitemap: {BASE}/sitemap.xml\n")

    # RSS
    def rfc(p):
        return format_datetime(datetime.fromisoformat(iso(p)))
    items = "".join(
        f"<item><title>{E(plain(p['title']))}</title><link>{url_post(p)}</link><guid isPermaLink=\"true\">{url_post(p)}</guid>"
        f"<pubDate>{rfc(p)}</pubDate><category>{E(p['topic'])}</category><description>{E(description(p))}</description>"
        f"<enclosure url=\"{BASE}/{p['id']}.jpg\" type=\"image/jpeg\" length=\"0\"/></item>\n" for p in posts[:50])
    write("feed.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>{NAME}</title><link>{BASE}/</link>'
          f"<description>Azərbaycan və dünyadan qısa, aydın xəbərlər</description><language>az</language>"
          f"<lastBuildDate>{rfc(posts[0])}</lastBuildDate>\n{items}</channel></rss>\n")

    update_index(posts)
    print(f"built {len(posts)} posts, {len(dlist)} days, {len(TOPICS)} topics -> {BASE}")


TOPICS = []
if __name__ == "__main__":
    main()

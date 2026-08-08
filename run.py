#!/usr/bin/env python3
"""Daily Fitness & Longevity Intelligence Dashboard generator."""

import json, base64, urllib.request, urllib.parse, subprocess, os
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

TG_TOKEN      = os.environ["TG_TOKEN"]
TG_CHAT_ID    = os.environ["TG_CHAT_ID"]
GH_TOKEN      = os.environ["GH_TOKEN"]
GH_REPO       = "manuelcasadeicom-bot/fitness-dashboard"
DASHBOARD_URL = "https://manuelcasadeicom-bot.github.io/fitness-dashboard/"

SUBSTACK_SOURCES = [
    ("https://staycuriousmetabolism.substack.com", "Stay Curious Metabolism"),
    ("https://neuroathletics.substack.com",        "Neuro Athletics"),
    ("https://chrismasterjohnphd.substack.com",    "Chris Masterjohn PhD"),
]

UA    = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
NOW   = datetime.now(timezone.utc)
PROXY = "https://reddit-proxy.manuelcasadei-com.workers.dev"

def curl_get(url):
    cmd = ["curl", "-sL", "--max-time", "25", "-A", UA,
           "-H", "Accept: text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.8",
           url]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"    curl error {r.returncode}: {r.stderr[:80]}")
    return r.stdout

def proxy_get(url):
    encoded = urllib.parse.quote(url, safe='')
    proxy_url = f"{PROXY}?url={encoded}"
    return curl_get(proxy_url)

def parse_date(s):
    if not s: return None
    s = s.strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT",
                "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except: pass
    return None

N_PER_SOURCE = 3  # articles per source for the dashboard

def fetch_json(base_url, name, n):
    """Try Substack JSON API: returns list of up to n items."""
    api = f"{base_url}/api/v1/posts/?limit={n}"
    raw = proxy_get(api)
    print(f"    JSON api: {len(raw)}b | {raw[:100]!r}")
    if not raw.strip(): return []
    data = json.loads(raw)
    posts = data if isinstance(data, list) else data.get("posts", [])
    result = []
    for p in posts[:n]:
        title = (p.get("title") or "").strip()[:120]
        link  = p.get("canonical_url") or f"{base_url}/p/{p.get('slug', '')}"
        dt    = parse_date(p.get("post_date") or "")
        if title:
            result.append({"title": title, "url": link, "date": dt, "source_label": name, "source_type": "substack"})
    return result

def fetch_rss(base_url, name, n):
    """Fallback: RSS feed — returns list of up to n items."""
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    raw = proxy_get(f"{base_url}/feed")
    print(f"    RSS feed: {len(raw)}b | {raw[:100]!r}")
    if not raw.strip(): return []
    root = ET.fromstring(raw)
    ch = root.find("channel")
    entries = (ch.findall("item") if ch is not None else []) or root.findall("atom:entry", ns)
    print(f"    RSS entries: {len(entries)}")
    result = []
    for e in entries[:n]:
        title_el = e.find("title")
        link_el  = e.find("link")
        date_el  = e.find("pubDate") or e.find("atom:published", ns)
        title = "".join(title_el.itertext()).strip()[:120] if title_el is not None else ""
        link  = ("".join(link_el.itertext()).strip() or link_el.get("href", "")) if link_el is not None else ""
        date_str = "".join(date_el.itertext()).strip() if date_el is not None else ""
        if title:
            result.append({"title": title, "url": link, "date": parse_date(date_str), "source_label": name, "source_type": "substack"})
    return result

def fetch_substack(n=N_PER_SOURCE):
    all_items = []
    for base_url, name in SUBSTACK_SOURCES:
        print(f"  [{name}]")
        source_items = []
        for fetcher, label in [(fetch_json, "JSON"), (fetch_rss, "RSS")]:
            try:
                source_items = fetcher(base_url, name, n)
                if source_items:
                    print(f"    -> OK via {label}: {len(source_items)} items, first: {source_items[0]['title'][:50]!r}")
                    break
                print(f"    -> {label}: empty, trying next")
            except Exception as e:
                print(f"    -> {label} error: {type(e).__name__}: {e}")
        if source_items:
            for item in source_items:
                dt = item.get("date")
                item["date"] = dt.isoformat() if isinstance(dt, datetime) else NOW.isoformat()
            all_items.extend(source_items)
        else:
            print(f"    -> FAILED all methods for {name}")
    return all_items

HTML = r"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Fitness &amp; Longevity Intelligence</title><script src="https://cdn.tailwindcss.com"></script><style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}.card{transition:box-shadow .15s;}.card:hover{box-shadow:0 4px 20px rgba(0,0,0,.1);}</style></head><body class="bg-gray-50 min-h-screen"><div class="bg-white border-b border-gray-200 sticky top-0 z-10"><div class="max-w-2xl mx-auto px-4 py-3"><h1 class="text-lg font-bold text-gray-900">📊 Fitness &amp; Longevity Intelligence</h1><p class="text-xs text-gray-500">Last updated: __DATE__</p></div></div><div class="max-w-2xl mx-auto px-4 py-4" id="cc"></div><div class="max-w-2xl mx-auto px-4 pb-8 text-center"><p class="text-xs text-gray-400">Updated daily at 7:00 AM · WellBeingSm Intelligence</p></div><script>const D=__DATA__;document.getElementById('cc').innerHTML=D.sort((a,b)=>new Date(b.date)-new Date(a.date)).map(item=>`<div class="card bg-white rounded-xl p-4 mb-3 border border-gray-100 shadow-sm"><div class="flex items-start justify-between gap-2"><div class="flex-1 min-w-0"><span class="text-xs font-semibold px-2 py-0.5 rounded-full bg-orange-500 text-white">${item.source_label}</span><h3 class="font-semibold text-gray-900 text-sm leading-snug mt-2">${item.title}</h3><p class="text-xs text-gray-400 mt-1">${new Date(item.date).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'})}</p></div><a href="${item.url}" target="_blank" rel="noopener" class="shrink-0 text-xs bg-gray-900 text-white px-3 py-1.5 rounded-lg font-medium hover:bg-gray-700 mt-0.5 ml-2">Read →</a></div></div>`).join('');</script></body></html>"""

def generate_html(items, date_str):
    return HTML.replace("__DATE__", date_str).replace("__DATA__", json.dumps(items, ensure_ascii=False))

def upload_to_github(html):
    content_b64 = base64.b64encode(html.encode()).decode()
    api_url = f"https://api.github.com/repos/{GH_REPO}/contents/index.html"
    headers = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    req = urllib.request.Request(api_url, headers=headers)
    sha = ""
    try:
        with urllib.request.urlopen(req) as r:
            sha = json.loads(r.read()).get("sha", "")
    except: pass
    payload = {"message": f"Dashboard {NOW.strftime('%Y-%m-%d')}", "content": content_b64}
    if sha: payload["sha"] = sha
    req2 = urllib.request.Request(api_url, data=json.dumps(payload).encode(), method="PUT", headers=headers)
    with urllib.request.urlopen(req2) as r:
        return json.loads(r.read()).get("commit", {}).get("sha", "")[:12]

def send_telegram(all_items):
    # One article per source (the most recent = first in list)
    seen = set()
    tg_items = []
    for item in all_items:
        if item["source_label"] not in seen:
            tg_items.append(item)
            seen.add(item["source_label"])

    lines = [
        "📊 FITNESS & LONGEVITY INTELLIGENCE",
        f"📅 {NOW.strftime('%d %b %Y')} — 07:00 AM", "",
        "📰 ULTIMI ARTICOLI SUBSTACK", "━━━━━━━━━━━━━━"
    ]
    for i, item in enumerate(tg_items, 1):
        t = item["title"][:75] + ("…" if len(item["title"]) > 75 else "")
        lines += [f"{i}. [{item['source_label']}] {t}", f"   {item['url']}", ""]
    lines += ["━━━━━━━━━━━━━━", f"📲 Full dashboard: {DASHBOARD_URL}"]
    result = subprocess.run(
        ["curl", "-s", "-X", "POST",
         f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
         "--data-urlencode", f"chat_id={TG_CHAT_ID}",
         "--data-urlencode", f"text={chr(10).join(lines)}",
         "--data-urlencode", "disable_web_page_preview=true"],
        capture_output=True, text=True)
    resp = json.loads(result.stdout)
    print(f"  Telegram ok={resp.get('ok')} tg_items={len(tg_items)} err={resp.get('description','')}")
    return resp.get("ok", False)

if __name__ == "__main__":
    print("=== Fetching Substack ===")
    items = fetch_substack(n=N_PER_SOURCE)
    print(f"=== Total: {len(items)} articles (dashboard) ===")
    html = generate_html(items, NOW.strftime("%d %b %Y — %H:%M UTC"))
    print("=== Uploading dashboard ===")
    commit = upload_to_github(html)
    print(f"  Commit: {commit}")
    print("=== Sending Telegram ===")
    ok = send_telegram(items)
    print(f"=== Done: {'OK' if ok else 'FAILED'} ===")

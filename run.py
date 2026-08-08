#!/usr/bin/env python3
"""Daily Fitness & Longevity Intelligence Dashboard generator."""

import json, base64, urllib.request, subprocess, os
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

# ── CREDENTIALS ─────────────────────────────────────────────────────────────────────────────
TG_TOKEN      = os.environ["TG_TOKEN"]
TG_CHAT_ID    = os.environ["TG_CHAT_ID"]
GH_TOKEN      = os.environ["GH_TOKEN"]
GH_REPO       = "manuelcasadeicom-bot/fitness-dashboard"
DASHBOARD_URL = "https://manuelcasadeicom-bot.github.io/fitness-dashboard/"

# ── SOURCES ────────────────────────────────────────────────────────────────────────────────
SUBSTACK_FEEDS = [
    ("https://staycuriousmetabolism.substack.com/feed", "Stay Curious Metabolism"),
    ("https://neuroathletics.substack.com/feed",        "Neuro Athletics"),
    ("https://chrismasterjohnphd.substack.com/feed",    "Chris Masterjohn PhD"),
]

UA  = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
NOW = datetime.now(timezone.utc)

def curl_get(url):
    cmd = ["curl", "-sL", "--max-time", "20", "-A", UA, url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  curl error for {url}: {result.stderr[:100]}")
    return result.stdout

def parse_date(s):
    if not s: return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT",
                "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(s.strip(), fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except: pass
    return None

def get_text(el):
    """Extract text from element, handling CDATA and nested text."""
    if el is None: return ""
    text = "".join(el.itertext()).strip()
    return text

def fetch_substack():
    items = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for url, name in SUBSTACK_FEEDS:
        try:
            # Fetch directly (no proxy) — Substack feeds are publicly accessible
            raw = curl_get(url)
            if not raw.strip():
                print(f"  {name}: empty response")
                continue
            root = ET.fromstring(raw)
            channel = root.find("channel")
            entries = channel.findall("item") if channel else root.findall("atom:entry", ns)
            print(f"  {name}: {len(entries)} items found")
            for entry in entries[:1]:
                title_el = entry.find("title")
                link_el  = entry.find("link")
                date_el  = entry.find("pubDate") or entry.find("atom:published", ns)
                title = get_text(title_el)[:120]
                link  = (get_text(link_el) or (link_el.get("href", "") if link_el is not None else "")).strip()
                dt    = parse_date(get_text(date_el))
                print(f"    title: {title[:60]!r}, link: {link[:60]}")
                items.append({
                    "title": title, "url": link,
                    "source_type": "substack", "source_label": name,
                    "date": dt.isoformat() if dt else NOW.isoformat()
                })
        except Exception as e:
            print(f"  {name}: ERROR {e}")
    return items

HTML = r"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Fitness &amp; Longevity Intelligence</title><script src="https://cdn.tailwindcss.com"></script><style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}.card{transition:box-shadow .15s;}.card:hover{box-shadow:0 4px 20px rgba(0,0,0,.1);}</style></head><body class="bg-gray-50 min-h-screen"><div class="bg-white border-b border-gray-200 sticky top-0 z-10"><div class="max-w-2xl mx-auto px-4 py-3"><h1 class="text-lg font-bold text-gray-900">Fitness &amp; Longevity Intelligence</h1><p class="text-xs text-gray-500">Last updated: __DATE__</p></div></div><div class="max-w-2xl mx-auto px-4 py-4" id="cc"></div><div class="max-w-2xl mx-auto px-4 pb-8 text-center"><p class="text-xs text-gray-400">Updated daily at 7:00 AM - WellBeingSm Intelligence</p></div><script>const D=__DATA__;document.getElementById('cc').innerHTML=D.sort((a,b)=>new Date(b.date)-new Date(a.date)).map(item=>'<div class="card bg-white rounded-xl p-4 mb-3 border border-gray-100 shadow-sm"><div class="flex items-start justify-between gap-2"><div class="flex-1 min-w-0"><span class="text-xs font-semibold px-2 py-0.5 rounded-full bg-orange-500 text-white">'+item.source_label+'</span><h3 class="font-semibold text-gray-900 text-sm leading-snug mt-2">'+item.title+'</h3></div><a href="'+item.url+'" target="_blank" rel="noopener" class="shrink-0 text-xs bg-gray-900 text-white px-3 py-1.5 rounded-lg font-medium hover:bg-gray-700 mt-0.5 ml-2">Read →</a></div></div>').join('');</script></body></html>"""

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

def send_telegram(items):
    lines = [
        "📊 FITNESS & LONGEVITY INTELLIGENCE",
        f"📅 {NOW.strftime('%d %b %Y')} — 07:00 AM", "",
        "📰 ULTIMI ARTICOLI SUBSTACK", "━━━━━━━━━━━━━━"
    ]
    for i, item in enumerate(items, 1):
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
    return json.loads(result.stdout).get("ok", False)

if __name__ == "__main__":
    print("Fetching Substack...")
    items = fetch_substack()
    print(f"  Total: {len(items)} articles")
    html = generate_html(items, NOW.strftime("%d %b %Y — %H:%M UTC"))
    print("Uploading to GitHub...")
    commit = upload_to_github(html)
    print(f"  Commit: {commit}")
    print("Sending Telegram...")
    ok = send_telegram(items)
    print(f"  Telegram: {'OK' if ok else 'FAILED'}")
    print("Done.")

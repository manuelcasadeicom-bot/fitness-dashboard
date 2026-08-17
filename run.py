#!/usr/bin/env python3
"""Daily Fitness & Longevity Intelligence Dashboard generator."""

import json, base64, urllib.request, urllib.parse, subprocess, os, time, re
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

TG_TOKEN      = os.environ["TG_TOKEN"]
TG_CHAT_ID    = os.environ["TG_CHAT_ID"]
GH_TOKEN      = os.environ["GH_TOKEN"]
GH_REPO       = "manuelcasadeicom-bot/fitness-dashboard"
DASHBOARD_URL = "https://manuelcasadeicom-bot.github.io/fitness-dashboard/"
SUBSTACK_COOKIE = os.environ.get("SUBSTACK_COOKIE", "")

SUBSTACK_SOURCES = [
    ("https://staycuriousmetabolism.substack.com", "Stay Curious Metabolism", "fitness"),
    ("https://neuroathletics.substack.com",        "Neuro Athletics",         "fitness"),
    ("https://chrismasterjohnphd.substack.com",    "Chris Masterjohn PhD",    "fitness"),
    ("https://thomisticinstitute.substack.com",    "Thomistic Institute",     "teologia"),
    ("https://itsallaboutlogic.substack.com",      "It's All About Logic",    "logica"),
]

UA    = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
NOW   = datetime.now(timezone.utc)
PROXY = "https://reddit-proxy.manuelcasadei-com.workers.dev"

def curl_get(url):
    cmd = ["curl", "-sL", "--max-time", "25", "-A", UA,
           "-H", "Accept: text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.8"]
    if SUBSTACK_COOKIE and "substack.com" in url:
        cmd += ["-H", f"Cookie: substack.sid={SUBSTACK_COOKIE}"]
    cmd.append(url)
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

def strip_html(s, limit=1200):
    """Strip HTML tags, collapse whitespace, and truncate for display."""
    text = re.sub(r'<[^>]+>', ' ', s or '')
    text = re.sub(r'\s+', ' ', text).strip()[:limit]
    return text.replace('`', "'").replace('${', '')

def translate_to_it(text):
    """Translate text to Italian using Google Translate free endpoint."""
    if not text.strip(): return text
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=it&dt=t&q={urllib.parse.quote(text[:1800])}"
        r = subprocess.run(["curl", "-sL", "--max-time", "15", url], capture_output=True, text=True)
        data = json.loads(r.stdout)
        return "".join(part[0] for part in data[0] if part[0])
    except Exception as e:
        print(f"    translate error: {e}")
        return text

def fetch_article_conclusion(url, max_chars=2000):
    """Fetch full article page and extract meaningful paragraphs (thesis + body + conclusions)."""
    if not url:
        return ""
    try:
        time.sleep(1)
        # If cookie is available, go direct (proxy can't forward auth)
        if SUBSTACK_COOKIE and "substack.com" in url:
            raw = curl_get(url)
        else:
            raw = proxy_get(url)
            if not raw or len(raw) < 2000:
                raw = curl_get(url)
        if not raw or len(raw) < 500:
            return ""
        raw = re.sub(r'<script[\s\S]*?</script>', '', raw, flags=re.IGNORECASE)
        raw = re.sub(r'<style[\s\S]*?</style>', '', raw, flags=re.IGNORECASE)
        paras = re.findall(r'<p[^>]*?>([\s\S]*?)</p>', raw, re.IGNORECASE)
        texts = [strip_html(p, limit=500).strip() for p in paras]
        texts = [t for t in texts if len(t) > 60]  # skip nav/short fragments
        # Remove duplicate/near-duplicate lines (paywall upsell often repeats)
        seen_starts = set()
        deduped = []
        for t in texts:
            key = t[:40].lower()
            if key not in seen_starts:
                seen_starts.add(key)
                deduped.append(t)
        texts = deduped
        print(f"    article conclusion: {len(texts)} paras from {len(raw)}b page")
        if not texts:
            return ""
        if len(texts) <= 6:
            return ' '.join(texts)[:max_chars]
        # First 2 paras (thesis/intro) + last 3 paras (conclusions/recommendations)
        result = ' '.join(texts[:2]) + ' … ' + ' '.join(texts[-3:])
        return result[:max_chars]
    except Exception as e:
        print(f"    article conclusion error: {e}")
        return ""

N_PER_SOURCE = 3  # articles per source for the dashboard

def fetch_json(base_url, name, n):
    """Try Substack JSON API: returns list of up to n items."""
    api = f"{base_url}/api/v1/posts/?limit={n}"
    # Use cookie directly when available — unlocks body_html for subscribed publications
    if SUBSTACK_COOKIE:
        raw = curl_get(api)
    else:
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
        subtitle = strip_html(p.get("subtitle") or p.get("description") or "", limit=400)
        # Fetch full article for conclusion paragraphs (thesis + recommendations)
        article_body = fetch_article_conclusion(link)
        if article_body:
            desc_raw = (subtitle + " — " + article_body) if subtitle and subtitle.lower() not in article_body.lower() else article_body
        else:
            # Fallback: use body_html (full content if authenticated) or truncated_body_text
            body_raw = p.get("body_html") or p.get("truncated_body_text") or ""
            body = strip_html(body_raw, limit=2000)
            desc_raw = (subtitle + " — " + body) if subtitle and body and subtitle.lower() not in body.lower() else (body or subtitle)
        desc = translate_to_it(desc_raw)
        if title:
            result.append({"title": title, "url": link, "date": dt, "source_label": name, "source_type": "substack", "description": desc})
    return result

def _parse_rss_raw(raw, base_url, name, n):
    """Parse RSS/Atom XML string; shared by proxy and direct fetchers."""
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    ns_content = "http://purl.org/rss/1.0/modules/content/"
    if not raw.strip(): return []
    root = ET.fromstring(raw)
    ch = root.find("channel")
    entries = (ch.findall("item") if ch is not None else []) or root.findall("atom:entry", ns)
    print(f"    RSS entries: {len(entries)}")
    result = []
    for e in entries[:n]:
        title_el   = e.find("title")
        link_el    = e.find("link")
        date_el    = e.find("pubDate") or e.find("atom:published", ns)
        desc_el    = e.find("description")
        content_el = e.find(f"{{{ns_content}}}encoded")  # content:encoded — full preview HTML
        title    = "".join(title_el.itertext()).strip()[:120] if title_el is not None else ""
        link     = ("".join(link_el.itertext()).strip() or link_el.get("href", "")) if link_el is not None else ""
        date_str = "".join(date_el.itertext()).strip() if date_el is not None else ""
        # content:encoded has the full preview (several paragraphs); description is just a teaser
        if content_el is not None and content_el.text:
            api_desc = strip_html(content_el.text, limit=2000)
            print(f"    content:encoded {len(content_el.text)}b → {len(api_desc)} chars")
        else:
            api_desc = strip_html("".join(desc_el.itertext()).strip() if desc_el is not None else "", limit=1000)
        article_body = fetch_article_conclusion(link)
        desc_raw = article_body if article_body else api_desc
        desc = translate_to_it(desc_raw)
        if title:
            result.append({"title": title, "url": link, "date": parse_date(date_str), "source_label": name, "source_type": "substack", "description": desc})
    return result

def fetch_rss(base_url, name, n):
    """Fallback: RSS feed via proxy — returns list of up to n items."""
    raw = proxy_get(f"{base_url}/feed")
    print(f"    RSS feed: {len(raw)}b | {raw[:100]!r}")
    return _parse_rss_raw(raw, base_url, name, n)

def fetch_rss_direct(base_url, name, n):
    """Last resort: RSS feed fetched directly (no proxy)."""
    raw = curl_get(f"{base_url}/feed")
    print(f"    RSS direct: {len(raw)}b | {raw[:100]!r}")
    return _parse_rss_raw(raw, base_url, name, n)

RETRY_DELAYS = [4, 8]  # seconds to wait before each retry of the same method

def fetch_substack(n=N_PER_SOURCE):
    all_items = []
    for i, (base_url, name, category) in enumerate(SUBSTACK_SOURCES):
        if i > 0:
            time.sleep(3)  # pause between sources to avoid rate limiting
        print(f"  [{name}]")
        source_items = []
        for fetcher, label in [(fetch_json, "JSON"), (fetch_rss, "RSS"), (fetch_rss_direct, "RSS-direct")]:
            # Try each fetcher up to 1+len(RETRY_DELAYS) times with backoff
            for attempt, delay in enumerate([0] + RETRY_DELAYS):
                if delay:
                    print(f"    -> {label} retry {attempt} in {delay}s...")
                    time.sleep(delay)
                try:
                    source_items = fetcher(base_url, name, n)
                    if source_items:
                        print(f"    -> OK via {label} (attempt {attempt+1}): {len(source_items)} items, first: {source_items[0]['title'][:50]!r}")
                        break
                    print(f"    -> {label} attempt {attempt+1}: empty")
                except Exception as e:
                    print(f"    -> {label} attempt {attempt+1} error: {type(e).__name__}: {e}")
            if source_items:
                break
            if label != "RSS-direct":
                time.sleep(3)  # pause between fallback methods
        if source_items:
            for item in source_items:
                dt = item.get("date")
                item["date"] = dt.isoformat() if isinstance(dt, datetime) else NOW.isoformat()
                item["category"] = category
            all_items.extend(source_items)
        else:
            print(f"    -> FAILED all methods for {name}")
    return all_items

HTML = r"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Fitness &amp; Longevity Intelligence</title><script src="https://cdn.tailwindcss.com"></script><style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}.card{transition:box-shadow .15s;}.card:hover{box-shadow:0 4px 20px rgba(0,0,0,.1);}</style></head><body class="bg-gray-50 min-h-screen"><div class="bg-white border-b border-gray-200 sticky top-0 z-10"><div class="max-w-2xl mx-auto px-4 py-3"><h1 class="text-lg font-bold text-gray-900">📊 Fitness &amp; Longevity Intelligence</h1><p class="text-xs text-gray-500">Last updated: __DATE__</p></div></div><div class="max-w-2xl mx-auto px-4 py-4" id="cc"></div><div class="max-w-2xl mx-auto px-4 pb-8 text-center"><p class="text-xs text-gray-400">Updated daily at 7:00 AM · WellBeingSm Intelligence</p></div><script>const D=__DATA__;const CO={fitness:0,teologia:1,logica:2};const CL={fitness:'🏋️ FITNESS & LONGEVITY',teologia:'✝️ TEOLOGIA',logica:'🧠 LOGICA'};const CC={fitness:'#f97316',teologia:'#7c3aed',logica:'#2563eb'};D.sort((a,b)=>{const d=(CO[a.category]??99)-(CO[b.category]??99);return d||new Date(b.date)-new Date(a.date);});let html='',cur=null;for(const item of D){if(item.category!==cur){cur=item.category;html+=`<div style="margin:20px 0 8px;padding-bottom:8px;border-bottom:2px solid #e5e7eb"><h2 style="font-size:14px;font-weight:700;color:#374151">${CL[cur]??cur}</h2></div>`;}const desc=item.description?`<details style="margin-top:8px"><summary style="cursor:pointer;font-size:12px;color:#9ca3af;list-style:none;outline:none">&#9656; Di cosa parla</summary><p style="font-size:13px;color:#374151;margin-top:8px;line-height:1.75;border-left:3px solid #e5e7eb;padding-left:10px">${item.description}</p></details>`:'';html+=`<div class="card bg-white rounded-xl p-4 mb-3 border border-gray-100 shadow-sm"><div class="flex items-start justify-between gap-2"><div class="flex-1 min-w-0"><span style="font-size:11px;font-weight:600;padding:2px 8px;border-radius:9999px;background:${CC[item.category]??'#6b7280'};color:white">${item.source_label}</span><h3 class="font-semibold text-gray-900 text-sm leading-snug mt-2">${item.title}</h3><p class="text-xs text-gray-400 mt-1">${new Date(item.date).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'})}</p>${desc}</div><a href="${item.url}" target="_blank" rel="noopener" class="shrink-0 text-xs bg-gray-900 text-white px-3 py-1.5 rounded-lg font-medium hover:bg-gray-700 mt-0.5 ml-2">Read →</a></div></div>`;}document.getElementById('cc').innerHTML=html;</script></body></html>"""

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
        "📊 INTELLIGENCE DAILY",
        f"📅 {NOW.strftime('%d %b %Y')} — 07:00 AM", "",
    ]
    sections = [
        ("fitness",  "🏋️ FITNESS & LONGEVITY"),
        ("teologia", "✝️ TEOLOGIA"),
        ("logica",   "🧠 LOGICA"),
    ]
    counter = 1
    for cat_key, cat_label in sections:
        cat_items = [i for i in tg_items if i.get("category") == cat_key]
        if not cat_items:
            continue
        lines += [cat_label, "━━━━━━━━━━━━━━"]
        for item in cat_items:
            t = item["title"][:75] + ("…" if len(item["title"]) > 75 else "")
            lines += [f"{counter}. [{item['source_label']}] {t}", f"   {item['url']}", ""]
            counter += 1
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

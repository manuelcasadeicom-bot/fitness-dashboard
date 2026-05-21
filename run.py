#!/usr/bin/env python3
"""Daily Fitness Intelligence & Economics Dashboard generator."""

import json, base64, urllib.request, subprocess, os
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET

# ── CREDENTIALS ───────────────────────────────────────────────────────────────
TG_TOKEN      = os.environ["TG_TOKEN"]
TG_CHAT_ID    = os.environ["TG_CHAT_ID"]
GH_TOKEN      = os.environ["GH_TOKEN"]
GH_REPO       = "manuelcasadeicom-bot/fitness-dashboard"
DASHBOARD_URL = "https://manuelcasadeicom-bot.github.io/fitness-dashboard/"

# ── SOURCES ───────────────────────────────────────────────────────────────────
REDDIT_SUBS = [
    "Biohackers", "bodybuilding", "crossfit", "Fitness",
    "intermittentfasting", "ketoscience", "longevity", "nutrition", "xxfitness"
]

SUBSTACK_FEEDS = [
    ("https://runlongrunhealthy.substack.com/feed",       "Run Long Run Healthy"),
    ("https://www.physiologicallyspeaking.com/feed",      "Physiologically Speaking"),
    ("https://staycuriousmetabolism.substack.com/feed",   "Stay Curious Metabolism"),
    ("https://metatrends.substack.com/feed",              "Metatrends"),
    ("https://neuroathletics.substack.com/feed",          "Neuro Athletics"),
]

BLOG_FEEDS = [
    ("https://podcast.foundmyfitness.com/rss.xml", "FoundMyFitness"),
    ("https://nutritionfacts.org/feed/",            "NutritionFacts"),
    ("https://theproof.com/feed/",                  "The Proof"),
]

ECONOMIST_FEED = "https://www.economist.com/latest/rss.xml"

UA     = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
NOW    = datetime.now(timezone.utc)
CUTOFF = NOW - timedelta(hours=48)

# ── HELPERS ───────────────────────────────────────────────────────────────────
def curl_get(url, extra_headers=None):
    cmd = ["curl", "-sL", "--max-time", "20", "-A", UA]
    if extra_headers:
        for k, v in extra_headers.items():
            cmd += ["-H", f"{k}: {v}"]
    cmd.append(url)
    return subprocess.run(cmd, capture_output=True, text=True).stdout

def parse_date(s):
    if not s:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT",
                "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(s.strip(), fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except:
            pass
    return None

def fmt_num(n):
    if not n:
        return "0"
    return f"{n/1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)

def virality(score, comments, created_utc):
    hours_old = (NOW.timestamp() - created_utc) / 3600
    return min(100, int((score + comments * 15) / max(hours_old, 0.5) / 5))

# ── REDDIT ────────────────────────────────────────────────────────────────────
REDDIT_PROXY = "https://reddit-proxy.manuelcasadei-com.workers.dev"

def fetch_reddit():
    # Una sola chiamata combinata per tutti i subreddit → evita rate limit
    combined = "+".join(REDDIT_SUBS)
    items = []
    try:
        raw  = curl_get(f"{REDDIT_PROXY}/{combined}")
        data = json.loads(raw)
        for p in data.get("data", {}).get("children", []):
            d = p.get("data", {})
            created = d.get("created_utc", 0)
            if (NOW.timestamp() - created) / 3600 > 48:
                continue
            score    = d.get("score", 0)
            comments = d.get("num_comments", 0)
            sub      = d.get("subreddit", "")
            items.append({
                "title":        d.get("title", "")[:120],
                "url":          "https://reddit.com" + d.get("permalink", ""),
                "source_type":  "reddit",
                "source_label": f"r/{sub}",
                "virality":     virality(score, comments, created),
                "score":        score,
                "comments":     comments,
                "date":         datetime.fromtimestamp(created, tz=timezone.utc).isoformat(),
            })
    except Exception as e:
        print(f"  Reddit combined: {e}")
    items.sort(key=lambda x: x["virality"], reverse=True)
    return items[:8]

# ── RSS ───────────────────────────────────────────────────────────────────────
def fetch_rss(feeds, source_type):
    items = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for url, name in feeds:
        try:
            raw  = curl_get(url)
            root = ET.fromstring(raw)
            channel  = root.find("channel")
            entries  = channel.findall("item") if channel else root.findall("atom:entry", ns)
            count = 0
            for entry in entries:
                if count >= 3:
                    break
                title_el = entry.find("title")
                link_el  = entry.find("link")
                date_el  = entry.find("pubDate") or entry.find("atom:published", ns)
                title    = (title_el.text or "").strip()[:120]
                if link_el is not None:
                    link = (link_el.text or link_el.get("href", "")).strip()
                else:
                    link = ""
                dt = parse_date((date_el.text or "").strip() if date_el is not None else "")
                if dt and dt < CUTOFF:
                    continue
                items.append({
                    "title":        title,
                    "url":          link,
                    "source_type":  source_type,
                    "source_label": name,
                    "virality":     None,
                    "score":        None,
                    "comments":     None,
                    "date":         dt.isoformat() if dt else NOW.isoformat(),
                })
                count += 1
        except Exception as e:
            print(f"  RSS {name}: {e}")
    return items

# ── ECONOMIST ─────────────────────────────────────────────────────────────────
def fetch_economist():
    items = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        raw  = curl_get(ECONOMIST_FEED)
        root = ET.fromstring(raw)
        channel = root.find("channel")
        entries = channel.findall("item") if channel else []
        for entry in entries[:5]:
            title_el = entry.find("title")
            link_el  = entry.find("link")
            desc_el  = entry.find("description")
            date_el  = entry.find("pubDate")
            title = (title_el.text or "").strip()[:120] if title_el is not None else ""
            link  = (link_el.text or "").strip() if link_el is not None else ""
            desc  = (desc_el.text or "").strip()[:200] if desc_el is not None else ""
            dt    = parse_date((date_el.text or "").strip() if date_el is not None else "")
            items.append({
                "title":        title,
                "url":          link,
                "source_type":  "economist",
                "source_label": "The Economist",
                "description":  desc,
                "virality":     None,
                "score":        None,
                "comments":     None,
                "date":         dt.isoformat() if dt else NOW.isoformat(),
            })
    except Exception as e:
        print(f"  Economist: {e}")
    return items

# ── HTML ──────────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Fitness Intelligence & Economics</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}
  .virality-high{background:#dcfce7;color:#166534;}
  .virality-mid{background:#fef9c3;color:#854d0e;}
  .virality-low{background:#fee2e2;color:#991b1b;}
  .source-reddit{background:#ff4500;color:white;}
  .source-substack{background:#ff6719;color:white;}
  .source-blog{background:#6366f1;color:white;}
  .source-economist{background:#B22222;color:white;}
  .card{transition:box-shadow .15s;}
  .card:hover{box-shadow:0 4px 20px rgba(0,0,0,.1);}
</style>
</head>
<body class="bg-gray-50 min-h-screen">
<div class="bg-white border-b border-gray-200 sticky top-0 z-10">
  <div class="max-w-2xl mx-auto px-4 py-3">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-lg font-bold text-gray-900">📊 Fitness Intelligence & Economics</h1>
        <p class="text-xs text-gray-500">Last updated: __DATE__</p>
      </div>
      <span class="text-xs text-gray-400" id="cnt"></span>
    </div>
    <div class="flex gap-2 mt-3 overflow-x-auto pb-1">
      <button class="fbtn active text-sm px-3 py-1.5 rounded-full border border-gray-200 bg-blue-700 text-white font-medium whitespace-nowrap" onclick="flt('all',this)">All</button>
      <button class="fbtn text-sm px-3 py-1.5 rounded-full border border-gray-200 text-gray-600 font-medium whitespace-nowrap" onclick="flt('reddit',this)">🔥 Reddit</button>
      <button class="fbtn text-sm px-3 py-1.5 rounded-full border border-gray-200 text-gray-600 font-medium whitespace-nowrap" onclick="flt('substack',this)">📰 Substack</button>
      <button class="fbtn text-sm px-3 py-1.5 rounded-full border border-gray-200 text-gray-600 font-medium whitespace-nowrap" onclick="flt('blog',this)">📝 Blog</button>
      <button class="fbtn text-sm px-3 py-1.5 rounded-full border border-gray-200 text-gray-600 font-medium whitespace-nowrap" onclick="flt('economist',this)">🗞️ Economist</button>
    </div>
    <div class="flex gap-2 mt-2">
      <span class="text-xs text-gray-400 self-center">Sort:</span>
      <button id="sv" class="text-xs px-2.5 py-1 rounded border border-blue-300 bg-blue-50 text-blue-700 font-medium" onclick="srt('virality')">⚡ Virality</button>
      <button id="sd" class="text-xs px-2.5 py-1 rounded border border-gray-200 text-gray-500" onclick="srt('date')">🕐 Date</button>
    </div>
  </div>
</div>
<div class="max-w-2xl mx-auto px-4 py-4" id="cc"></div>
<div class="max-w-2xl mx-auto px-4 pb-8 text-center">
  <p class="text-xs text-gray-400">Updated daily at 7:00 AM · WellBeingSm Intelligence</p>
</div>
<script>
const D=__DATA__;
let cf='all',cs='virality';
const vc=v=>v==null?'':v>=70?'virality-high':v>=40?'virality-mid':'virality-low';
const fn=n=>!n?'0':n>=1000?(n/1000).toFixed(1).replace(/\.0$/,'')+'k':String(n);
function render(){
  let items=[...D];
  if(cf!=='all')items=items.filter(i=>i.source_type===cf);
  cs==='virality'?items.sort((a,b)=>(b.virality??-1)-(a.virality??-1)):items.sort((a,b)=>new Date(b.date)-new Date(a.date));
  document.getElementById('cnt').textContent=items.length+' items';
  const cc=document.getElementById('cc');
  if(!items.length){cc.innerHTML='<div class="text-center py-12 text-gray-400"><p class="text-4xl mb-2">🔍</p><p>No content in this category.</p></div>';return;}
  cc.innerHTML=items.map(item=>{
    const sb='source-'+item.source_type;
    const vb=item.virality!=null?`<span class="text-xs font-bold px-2 py-0.5 rounded-full ${vc(item.virality)}">⚡ ${item.virality}/100</span>`:'';
    const bar=item.virality!=null?`<div class="w-full bg-gray-100 rounded-full h-1.5 mt-2"><div style="width:${Math.min(100,item.virality)}%;background:${item.virality>=70?'#16a34a':item.virality>=40?'#ca8a04':'#dc2626'}" class="h-1.5 rounded-full"></div></div>`:'';
    const eng=item.source_type==='reddit'?`<div class="flex items-center gap-3 text-xs text-gray-500 mt-1"><span>⬆️ ${fn(item.score)}</span><span>💬 ${fn(item.comments)}</span>${vb}</div>${bar}`:`<div class="mt-1">${vb}</div>`;
    return`<div class="card bg-white rounded-xl p-4 mb-3 border border-gray-100 shadow-sm"><div class="flex items-start justify-between gap-2"><div class="flex-1 min-w-0"><div class="flex items-center gap-2 mb-1.5"><span class="text-xs font-semibold px-2 py-0.5 rounded-full ${sb}">${item.source_label}</span></div><h3 class="font-semibold text-gray-900 text-sm leading-snug">${item.title}</h3>${eng}</div><a href="${item.url}" target="_blank" rel="noopener" class="shrink-0 text-xs bg-gray-900 text-white px-3 py-1.5 rounded-lg font-medium hover:bg-gray-700 mt-0.5 ml-2">Read →</a></div></div>`;
  }).join('');
}
function flt(t,btn){cf=t;document.querySelectorAll('.fbtn').forEach(b=>{b.classList.remove('bg-blue-700','text-white');b.classList.add('text-gray-600');});btn.classList.add('bg-blue-700','text-white');btn.classList.remove('text-gray-600');render();}
function srt(t){cs=t;document.getElementById('sv').className=`text-xs px-2.5 py-1 rounded border font-medium ${t==='virality'?'border-blue-300 bg-blue-50 text-blue-700':'border-gray-200 text-gray-500'}`;document.getElementById('sd').className=`text-xs px-2.5 py-1 rounded border font-medium ${t==='date'?'border-blue-300 bg-blue-50 text-blue-700':'border-gray-200 text-gray-500'}`;render();}
render();
</script>
</body>
</html>"""

def generate_html(items, date_str):
    return HTML.replace("__DATE__", date_str).replace("__DATA__", json.dumps(items, ensure_ascii=False))

# ── GITHUB UPLOAD ─────────────────────────────────────────────────────────────
def upload_to_github(html):
    content_b64 = base64.b64encode(html.encode("utf-8")).decode("ascii")
    api_url = f"https://api.github.com/repos/{GH_REPO}/contents/index.html"
    headers = {
        "Authorization": f"token {GH_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(api_url, headers={k: v for k, v in headers.items() if k != "Content-Type"})
    sha = ""
    try:
        with urllib.request.urlopen(req) as r:
            sha = json.loads(r.read()).get("sha", "")
    except:
        pass
    payload = {"message": f"Dashboard {NOW.strftime('%Y-%m-%d')}", "content": content_b64}
    if sha:
        payload["sha"] = sha
    req2 = urllib.request.Request(api_url, data=json.dumps(payload).encode(), method="PUT", headers=headers)
    with urllib.request.urlopen(req2) as r:
        return json.loads(r.read()).get("commit", {}).get("sha", "")[:12]

# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def send_telegram(all_items):
    top3 = sorted([i for i in all_items if i["virality"] is not None],
                  key=lambda x: x["virality"], reverse=True)[:3]
    lines = [
        "📊 FITNESS & LONGEVITY INTELLIGENCE",
        f"📅 {NOW.strftime('%d %b %Y')} — 07:00 AM",
        "",
        "🏆 TOP 3 TODAY",
        "━━━━━━━━━━━━━━",
    ]
    for i, item in enumerate(top3, 1):
        t = item["title"][:75] + ("…" if len(item["title"]) > 75 else "")
        lines += [
            f"{i}. [{item['source_label']}] {t}",
            f"   ⬆️ {fmt_num(item['score'])}  💬 {fmt_num(item['comments'])}  ⚡ {item['virality']}/100",
            f"   {item['url']}",
            "",
        ]
    lines += ["━━━━━━━━━━━━━━", f"📲 Full dashboard: {DASHBOARD_URL}"]
    msg = "\n".join(lines)
    result = subprocess.run([
        "curl", "-s", "-X", "POST",
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        "--data-urlencode", f"chat_id={TG_CHAT_ID}",
        "--data-urlencode", f"text={msg}",
        "--data-urlencode", "disable_web_page_preview=true",
    ], capture_output=True, text=True)
    return json.loads(result.stdout).get("ok", False)

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Fetching Reddit...")
    reddit = fetch_reddit()
    print(f"  {len(reddit)} posts")

    print("Fetching Substack...")
    substack = fetch_rss(SUBSTACK_FEEDS, "substack")
    print(f"  {len(substack)} posts")

    print("Fetching blogs...")
    blogs = fetch_rss(BLOG_FEEDS, "blog")
    print(f"  {len(blogs)} posts")

    print("Fetching Economist...")
    economist = fetch_economist()
    print(f"  {len(economist)} articles")

    all_items = reddit + substack + blogs + economist
    print(f"Total: {len(all_items)} items")

    date_str = NOW.strftime("%d %b %Y — %H:%M UTC")
    html = generate_html(all_items, date_str)

    print("Uploading to GitHub...")
    commit = upload_to_github(html)
    print(f"  Commit: {commit}")

    print("Sending Telegram...")
    ok = send_telegram(all_items)
    print(f"  Telegram: {'OK' if ok else 'FAILED'}")

    print("Done.")

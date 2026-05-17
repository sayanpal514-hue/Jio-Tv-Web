#!/usr/bin/env python3
"""
generate_channel.py
-------------------
Fetches the JioTV M3U playlist, parses each channel's stream URL and
ClearKey DRM credentials, then generates a self-contained HTML player
page for every channel inside the  channel/  directory.

Usage:
    python generate_channel.py
"""

import os
import re
import json
import base64
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

# Remote M3U playlist URL (set to "" to skip and use LOCAL_M3U_PATH instead)
M3U_URL = "https://jiotvplus.dr-strange.workers.dev/api/jiotvplus.m3u"

# Local M3U fallback — set this path if the remote URL is unavailable
# Example: LOCAL_M3U_PATH = r"d:\Jio Tv +\jiotv.m3u"
LOCAL_M3U_PATH = ""


OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "channel")

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def fetch_text(url: str, timeout: int = 15) -> str:
    """Download a URL and return its text content."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 Chrome/124 Safari/537.36"
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def slug(name: str) -> str:
    """Convert a channel name to a safe filename slug."""
    name = name.lower().strip()
    name = re.sub(r"[^\w\s-]", "", name)       # remove special chars
    name = re.sub(r"[\s_]+", "-", name)         # spaces → hyphens
    name = re.sub(r"-{2,}", "-", name)           # collapse double hyphens
    return name.strip("-") or "channel"


def b64url_to_hex(b64: str) -> str:
    """Convert a base64url string (no padding) to a lowercase hex string."""
    # Add padding
    padded = b64 + "=" * (-len(b64) % 4)
    return base64.urlsafe_b64decode(padded).hex()


def parse_clearkey(license_key_str: str):
    """
    Extract (key_id_hex, key_hex) from a KODIPROP clearkey license string.

    Accepts two common formats:
      1. JSON  → {"keys":[{"kty":"oct","k":"<b64>","kid":"<b64>"}],"type":"temporary"}
      2. Plain → <key_id_hex>:<key_hex>
    """
    license_key_str = license_key_str.strip()

    # --- Format 1: JSON ---
    if license_key_str.startswith("{"):
        try:
            obj = json.loads(license_key_str)
            for entry in obj.get("keys", []):
                kid_hex = b64url_to_hex(entry["kid"])
                k_hex   = b64url_to_hex(entry["k"])
                return kid_hex, k_hex
        except (json.JSONDecodeError, KeyError, Exception):
            pass

    # --- Format 2: hex:hex ---
    if ":" in license_key_str:
        parts = license_key_str.split(":", 1)
        if len(parts) == 2 and all(re.fullmatch(r"[0-9a-fA-F]+", p.strip()) for p in parts):
            return parts[0].strip().lower(), parts[1].strip().lower()

    return None, None


def parse_m3u(content: str):
    """
    Parse an M3U playlist and return a list of channel dicts:
        {name, logo, group, stream_url, key_id, key}
    """
    channels = []
    lines = content.splitlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line.startswith("#EXTINF"):
            i += 1
            continue

        # --- Parse #EXTINF attributes ---
        name  = ""
        logo  = ""
        group = ""

        name_match = re.search(r",(.+)$", line)
        if name_match:
            name = name_match.group(1).strip()

        logo_match  = re.search(r'tvg-logo="([^"]*)"', line)
        group_match = re.search(r'group-title="([^"]*)"', line)
        if logo_match:
            logo = logo_match.group(1)
        if group_match:
            group = group_match.group(1)

        # --- Scan following lines for KODIPROP / stream URL ---
        key_id = ""
        key    = ""
        stream_url = ""

        j = i + 1
        while j < len(lines):
            nxt = lines[j].strip()

            if nxt.startswith("#KODIPROP:inputstream.adaptive.license_key"):
                # e.g.  #KODIPROP:inputstream.adaptive.license_key={"keys":...}
                val = nxt.split("=", 1)[1] if "=" in nxt else ""
                key_id, key = parse_clearkey(val)

            elif nxt.startswith("#"):
                pass  # other directive — skip

            elif nxt:  # non-empty, non-comment → stream URL
                stream_url = nxt.split("|")[0].strip()
                j += 1
                break

            j += 1

        i = j  # advance outer pointer past the block we just consumed

        if stream_url and name:
            channels.append(
                {
                    "name":       name,
                    "logo":       logo,
                    "group":      group,
                    "stream_url": stream_url,
                    "key_id":     key_id or "",
                    "key":        key    or "",
                }
            )

    return channels


# ---------------------------------------------------------------------------
# HTML TEMPLATE
# ---------------------------------------------------------------------------


HTML_TEMPLATE_76 = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%%CHANNEL_NAME%% | Sayan</title>
<meta name="referrer" content="no-referrer">
<script src="https://cdn.jsdelivr.net/npm/shaka-player@4.16.2/dist/shaka-player.ui.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/shaka-player@4.16.2/dist/controls.css"/>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">

<style>
:root {
    --primary: #ff3c3c;
    --bg: #000;
    --surface: rgba(255, 255, 255, 0.05);
    --glass: rgba(0, 0, 0, 0.6);
}

*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;background:var(--bg);overflow:hidden;font-family:'Outfit', sans-serif}

.shaka-video-container{
position:fixed;
inset:0;
background:#000;
display:flex;
align-items:center;
justify-content:center;
}

video{
width:100%;
height:100%;
object-fit:contain;
}

/* Header/Overlay */
.player-header {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    padding: 15px 25px;
    background: linear-gradient(to bottom, rgba(0,0,0,0.8) 0%, transparent 100%);
    z-index: 100;
    display: flex;
    align-items: center;
    gap: 15px;
    transition: opacity 0.3s ease;
}

.back-btn {
    color: white;
    text-decoration: none;
    font-size: 24px;
    background: rgba(255,255,255,0.1);
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    backdrop-filter: blur(10px);
    transition: all 0.3s;
}

.back-btn:hover { background: var(--primary); transform: scale(1.1); }

.channel-info { display: flex; align-items: center; gap: 12px; }

.channel-logo {
    height: 35px;
    width: auto;
    max-width: 100px;
    object-fit: contain;
    filter: drop-shadow(0 0 10px rgba(0,0,0,0.5));
}

.channel-name {
    color: white;
    font-weight: 700;
    font-size: 18px;
    text-shadow: 0 2px 10px rgba(0,0,0,0.5);
}

.custom-watermark{
position:absolute;
z-index:40;
pointer-events:none;
top:15%;
right:5%;
font-size:12px;
font-weight:800;
color:rgba(255,255,255,0.15);
letter-spacing: 1px;
}

/* --- Block Overlay --- */
.block-overlay{
position:fixed;
inset:0;
z-index:99999;
display:flex;
align-items:center;
justify-content:center;
background:radial-gradient(circle at center, #1a1a1a 0%, #000000 100%);
text-align:center;
}

.block-box{
padding:40px;
max-width:500px;
width:90%;
background:rgba(20, 20, 20, 0.95);
border-radius:16px;
border:1px solid rgba(255, 255, 255, 0.1);
box-shadow:0 20px 50px rgba(0,0,0,0.5);
}

.block-title{ font-size:32px; font-weight:800; color:#fff; margin-bottom:15px; text-transform: uppercase;}
.block-sub{ font-size:14px; color:rgba(255,255,255,0.6); line-height:1.6; }

@media(max-width:700px){
    .player-header { padding: 10px 15px; }
    .channel-name { font-size: 15px; }
    .channel-logo { height: 25px; }
}
</style>
</head>
<body>

<div class="player-header" id="header">
    <a href="../index.html" class="back-btn">←</a>
    <div class="channel-info">
        <img src="%%CHANNEL_LOGO%%" alt="" class="channel-logo" onerror="this.style.display='none'">
        <span class="channel-name">%%CHANNEL_NAME%%</span>
    </div>
</div>

<div class="shaka-video-container" id="player-container">
    <video id="video" autoplay muted playsinline preload="metadata"></video>
    <div class="custom-watermark">SAYAN</div>
</div>

<script>
(function(){
  
  function isSandboxedEnv(){
    try {
      if (window.self === window.top) return false;
      if (window.frameElement && window.frameElement.hasAttribute("sandbox")) return true;
      try {
        document.domain = document.domain;
        if (window.frameElement && !window.frameElement.getAttribute("sandbox")) return false;
      } catch (e) { return true; }
      return false;
    } catch(e) { return true; }
  }

  function triggerBlockScreen(title, message){
    const container = document.getElementById("player-container");
    const video = document.getElementById("video");
    try {
      video.pause();
      video.removeAttribute('src');
      video.load();
    } catch(e){}

    const overlay = document.createElement("div");
    overlay.className = "block-overlay";
    overlay.innerHTML = `
      <div class="block-box">
        <div class="block-title">${title}</div>
        <div class="block-sub">${message}</div>
      </div>
    `;
    document.body.appendChild(overlay);
    container.style.display = 'none';
    document.getElementById('header').style.display = 'none';
  }

  if(isSandboxedEnv()){
    triggerBlockScreen('Access Denied', 'Please open in a standard browser and disable ad-blockers.');
    return;
  }

  const CONFIG={
    streamUrl:"%%STREAM_URL%%",
    keyId:"%%KEY_ID%%",
    key:"%%KEY%%",
    cookie:"%%CHANNEL_COOKIE%%"
  };

  document.addEventListener("DOMContentLoaded",async()=>{
    shaka.polyfill.installAll();
    if(!shaka.Player.isBrowserSupported()) return;

    const video=document.getElementById("video");
    const container=document.getElementById("player-container");
    const header=document.getElementById("header");

    let hideTimeout;
    const showHeader = () => {
        header.style.opacity = '1';
        clearTimeout(hideTimeout);
        hideTimeout = setTimeout(() => {
            header.style.opacity = '0';
        }, 3000);
    };
    container.addEventListener('mousemove', showHeader);
    container.addEventListener('touchstart', showHeader);
    showHeader();

    const player=new shaka.Player();
    await player.attach(video);

    const ui=new shaka.ui.Overlay(player,container,video);
    ui.configure({
      addBigPlayButton: true,
      controlPanelElements: ["mute","play_pause","time_and_duration","spacer","quality","picture_in_picture","fullscreen"]
    });

    const drmConfig = {};
    if (CONFIG.keyId && CONFIG.key) {
      drmConfig.clearKeys = {[CONFIG.keyId]: CONFIG.key};
    }

    player.configure({
      drm: drmConfig,
      manifest:{defaultPresentationDelay:5},
      streaming:{ lowLatencyMode:true, bufferingGoal:10, rebufferingGoal:2 }
    });

    player.getNetworkingEngine().registerRequestFilter((type,request)=>{
        request.headers["Referer"]="https://www.jiotv.com/";
        request.headers["User-Agent"]="plaYtv/7.1.5 (Linux;Android 13) ExoPlayerLib/2.11.6";
        
        if(CONFIG.cookie){
            request.headers["Cookie"]=CONFIG.cookie;
            let urlCookie=CONFIG.cookie.startsWith("__hdnea__=")?CONFIG.cookie.substring(10):CONFIG.cookie;
            if((type===shaka.net.NetworkingEngine.RequestType.MANIFEST||
                type===shaka.net.NetworkingEngine.RequestType.SEGMENT)&&
                !request.uris[0].includes("__hdnea__")){
                const sep=request.uris[0].includes("?")?"&":"?";
                request.uris[0]+=sep+"__hdnea__="+urlCookie;
            }
        }
    });

    try{
      await player.load(CONFIG.streamUrl);
      video.play().catch(()=>{});
    }catch(e){}

    video.addEventListener("play",()=>{ video.muted=false; });
  });
})();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# DASHBOARD TEMPLATE
# ---------------------------------------------------------------------------

DASHBOARD_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JioTV Dashboard - Sayan</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #ff3e3e;
            --bg: #0a0a0b;
            --card-bg: #161618;
            --text: #ffffff;
            --text-dim: #a0a0a0;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Outfit', sans-serif;
        }

        body {
            background-color: var(--bg);
            color: var(--text);
            padding: 20px;
            min-height: 100vh;
        }

        header {
            max-width: 1200px;
            margin: 0 auto 40px;
            text-align: center;
        }

        h1 {
            font-size: 3rem;
            font-weight: 800;
            margin-bottom: 10px;
            background: linear-gradient(to right, #fff, #ff3e3e);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .search-container {
            position: sticky;
            top: 20px;
            z-index: 100;
            max-width: 600px;
            margin: 0 auto 30px;
        }

        #search {
            width: 100%;
            padding: 15px 25px;
            border-radius: 30px;
            border: 1px solid rgba(255,255,255,0.1);
            background: rgba(22, 22, 24, 0.8);
            backdrop-filter: blur(10px);
            color: white;
            font-size: 1.1rem;
            outline: none;
            transition: all 0.3s;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
        }

        #search:focus {
            border-color: var(--primary);
            box-shadow: 0 0 20px rgba(255, 62, 62, 0.2);
        }

        .channel-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
            gap: 20px;
            max-width: 1200px;
            margin: 0 auto;
        }

        .channel-card {
            background: var(--card-bg);
            border-radius: 16px;
            padding: 20px;
            text-decoration: none;
            color: inherit;
            text-align: center;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border: 1px solid rgba(255,255,255,0.05);
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 15px;
        }

        .channel-card:hover {
            transform: translateY(-5px);
            background: #1c1c1f;
            border-color: var(--primary);
            box-shadow: 0 10px 30px rgba(0,0,0,0.4);
        }

        .logo-container {
            width: 100px;
            height: 100px;
            background: #000;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }

        .logo-container img {
            max-width: 80%;
            max-height: 80%;
            object-fit: contain;
        }

        .channel-name {
            font-weight: 600;
            font-size: 1rem;
            line-height: 1.2;
            height: 2.4em;
            overflow: hidden;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
        }

        .channel-group {
            font-size: 0.8rem;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        @media (max-width: 600px) {
            .channel-grid {
                grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
                gap: 15px;
            }
            h1 { font-size: 2rem; }
        }
    </style>
</head>
<body>
    <header>
        <h1>JioTV Mini</h1>
        <p style="color: var(--text-dim)">Premium channels</p>
    </header>

    <div class="search-container">
        <input type="text" id="search" placeholder="Search for channels..." autocomplete="off">
    </div>

    <div class="channel-grid" id="grid">
        %%CHANNELS_HTML%%
    </div>

    <script>
        const search = document.getElementById('search');
        const cards = document.querySelectorAll('.channel-card');

        search.addEventListener('input', (e) => {
            const term = e.target.value.toLowerCase();
            cards.forEach(card => {
                const name = card.dataset.name.toLowerCase();
                const group = card.dataset.group.toLowerCase();
                if (name.includes(term) || group.includes(term)) {
                    card.style.display = 'flex';
                } else {
                    card.style.display = 'none';
                }
            });
        });
    </script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # --- Fetch / read M3U ---
    m3u_content = ""
    if M3U_URL:
        print(f"[+] Fetching M3U playlist from:\n    {M3U_URL}")
        try:
            m3u_content = fetch_text(M3U_URL)
            print("[+] Remote M3U fetched successfully.")
        except urllib.error.URLError as e:
            print(f"[!] Remote fetch failed: {e}")

    if not m3u_content:
        print("[!] No M3U content available.")
        return

    # --- Parse channels ---
    channels = parse_m3u(m3u_content)
    print(f"[+] Found {len(channels)} channels in M3U")

    # --- Generate HTML files ---
    generated = 0
    skipped   = 0
    dashboard_items = []

    # Use HTML_TEMPLATE_76 as the unified template
    template = HTML_TEMPLATE_76

    for ch in channels:
        slug_name = slug(ch["name"])
        filename = slug_name + ".html"
        filepath = os.path.join(OUTPUT_DIR, filename)

        # Extract cookie from stream_url if present
        channel_cookie = ""
        if "__hdnea__=" in ch["stream_url"]:
            token = ch["stream_url"].split("__hdnea__=")[1].split("&")[0]
            channel_cookie = "__hdnea__=" + token
        
        html = (
            template
            .replace("%%CHANNEL_NAME%%", ch["name"])
            .replace("%%CHANNEL_LOGO%%", ch["logo"])
            .replace("%%STREAM_URL%%",   ch["stream_url"])
            .replace("%%KEY_ID%%",       ch["key_id"])
            .replace("%%KEY%%",          ch["key"])
            .replace("%%CHANNEL_COOKIE%%", channel_cookie)
        )

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)
            generated += 1
            
            # Card HTML for dashboard
            card_html = (
                f'<a href="channel/{filename}" class="channel-card" data-name="{ch["name"]}" data-group="{ch["group"]}">'
                f'  <div class="logo-container"><img src="{ch["logo"]}" onerror="this.src=\'https://www.jiotv.com/images/jiotv_logo.png\'"></div>'
                f'  <div class="channel-name">{ch["name"]}</div>'
                f'  <div class="channel-group">{ch["group"]}</div>'
                f'</a>'
            )
            dashboard_items.append(card_html)
                
        except OSError as e:
            print(f"  [ERR] {filename}: {e}")
            skipped += 1

    # --- Generate Dashboard ---
    dashboard_html = DASHBOARD_TEMPLATE.replace("%%CHANNELS_HTML%%", "\n".join(dashboard_items))
    try:
        with open(os.path.join(os.path.dirname(__file__), "index.html"), "w", encoding="utf-8") as f:
            f.write(dashboard_html)
        print("[+] Dashboard index.html generated successfully.")
    except OSError as e:
        print(f"[!] Failed to generate dashboard: {e}")

    print(f"\n[+] Done — {generated} files written, {skipped} skipped.")

if __name__ == "__main__":
    main()

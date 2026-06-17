import os
import re
import requests
import json
import shutil
import base64
import time
from concurrent.futures import ThreadPoolExecutor

# Configuration
M3U_URL = "https://raw.githubusercontent.com/opensourceflix/Friday/refs/heads/main/tmp/%25/privates.m3u8"
OUTPUT_DIR = "channel"

# Ensure output directory exists and is clean
if os.path.exists(OUTPUT_DIR):
    for filename in os.listdir(OUTPUT_DIR):
        file_path = os.path.join(OUTPUT_DIR, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}', flush=True)
else:
    os.makedirs(OUTPUT_DIR)

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{CHANNEL_TITLE}</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/shaka-player/4.7.11/shaka-player.ui.min.js" crossorigin="anonymous"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/shaka-player/4.7.11/controls.min.css" crossorigin="anonymous">
  <!-- Google tag (gtag.js) -->
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-FMP9REY96D"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){dataLayer.push(arguments);}
    gtag('js', new Date());
    gtag('config', 'G-FMP9REY96D');
  </script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      background: #000;
      height: 100vh;
      width: 100vw;
      overflow: hidden;
      font-family: system-ui, -apple-system, sans-serif;
    }
    .shaka-video-container {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
    }
    video {
      width: 100%;
      height: 100%;
      background: #000;
      object-fit: contain;
    }
    .shaka-spinner-container,
    .shaka-spinner,
    .shaka-spinner-svg {
      display: none !important;
      visibility: hidden !important;
      opacity: 0 !important;
    }
  </style>
</head>
<body>
  <div class="shaka-video-container" data-shaka-player>
    <video autoplay playsinline preload="metadata" poster=""></video>
  </div>

  <script>
    document.addEventListener('DOMContentLoaded', async () => {
      shaka.polyfill.installAll();

      if (!shaka.Player.isBrowserSupported()) {
        console.error('Browser not supported');
        return;
      }

      const video = document.querySelector('video');
      const player = new shaka.Player();
      await player.attach(video);

      const container = document.querySelector('.shaka-video-container');
      const ui = new shaka.ui.Overlay(player, container, video);

      ui.configure({
        controlPanelElements: [
          'play_pause', 'time_and_duration', 'mute', 'volume',
          'spacer', 'language', 'captions', 'picture_in_picture',
          'quality', 'fullscreen'
        ],
        volumeBarColors: {
          base: 'rgba(0, 136, 255, 0.3)',
          level: 'rgb(0, 136, 255)'
        },
        seekBarColors: {
          base: 'rgba(0, 136, 255, 0.3)',
          buffered: 'rgba(0, 136, 255, 0.6)',
          played: 'rgb(0, 136, 255)'
        }
      });

      const CONFIG = {
        streamUrl: "{STREAM_URL}",
        keyId: "{KEY_ID}",
        key: "{KEY}",
        licenseUrl: "{LICENSE_URL}",
        cookie: "{COOKIE}"
      };

      let drmConfig = {};
      if (CONFIG.keyId && CONFIG.key) {
        drmConfig = {
          clearKeys: {
            [CONFIG.keyId]: CONFIG.key
          }
        };
      } else if (CONFIG.licenseUrl) {
        drmConfig = {
          servers: { 'com.widevine.alpha': CONFIG.licenseUrl }
        };
      }

      player.configure({
        drm: drmConfig,
        streaming: {
          lowLatencyMode: true,
          bufferingGoal: 15,
          rebufferingGoal: 2,
          bufferBehind: 15,
          retryParameters: {
            timeout: 10000,
            maxAttempts: 5,
            baseDelay: 300,
            backoffFactor: 1.2
          },
          segmentRequestTimeout: 8000,
          segmentPrefetchLimit: 2,
          useNativeHlsOnSafari: true
        },
        manifest: {
          retryParameters: {
            timeout: 8000,
            maxAttempts: 3
          }
        }
      });

      player.getNetworkingEngine().registerRequestFilter((type, request) => {
        request.headers["Referer"] = "https://www.jiotv.com/";
        request.headers["User-Agent"] = "plaYtv/7.1.5 (Linux;Android 13) ExoPlayerLib/2.11.6";

        if (CONFIG.cookie) {
          request.headers["Cookie"] = CONFIG.cookie;
          let urlCookie = CONFIG.cookie.startsWith("__hdnea__=") ? CONFIG.cookie.substring(10) : CONFIG.cookie;
          if ((type === shaka.net.NetworkingEngine.RequestType.MANIFEST ||
               type === shaka.net.NetworkingEngine.RequestType.SEGMENT) &&
              !request.uris[0].includes("__hdnea__")) {
            const sep = request.uris[0].includes("?") ? "&" : "?";
            request.uris[0] += sep + "__hdnea__=" + urlCookie;
          }
        }
      });

      player.addEventListener('error', (event) => {
        console.error('Shaka Player Error:', event.detail);
      });

      try {
        await player.load(CONFIG.streamUrl);
        console.log("Stream loaded successfully");
      } catch (error) {
        console.error('Load error:', error);
      }
    });
  </script>
  <script>(function(s){s.dataset.zone='10603308',s.src='https://bvtpk.com/tag.min.js'})([document.documentElement, document.body].filter(Boolean).pop().appendChild(document.createElement('script')))</script>
</body>
</html>"""

def b64url_to_hex(b64):
    padding = '=' * (4 - len(b64) % 4)
    b64 = b64.replace('-', '+').replace('_', '/') + padding
    return base64.b64decode(b64).hex()

def fetch_key(url, session, cookie=None, retries=3):
    if not url or not url.startswith("http"):
        return None, None, url
    for i in range(retries):
        try:
            headers = {
                'User-Agent': 'plaYtv/7.1.5 (Linux;Android 13) ExoPlayerLib/2.11.6',
                'Referer': 'https://www.jiotv.com/'
            }
            if cookie:
                headers['Cookie'] = cookie
            resp = session.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if "keys" in data and len(data["keys"]) > 0:
                        kid_b64 = data["keys"][0]["kid"]
                        k_b64 = data["keys"][0]["k"]
                        return b64url_to_hex(kid_b64), b64url_to_hex(k_b64), ""
                except: pass
            elif resp.status_code == 429: time.sleep(1)
        except Exception:
            if i == retries - 1: pass
    return "", "", url

def generate():
    print(f"Fetching M3U from {M3U_URL}...", flush=True)
    try:
        response = requests.get(M3U_URL, timeout=30)
        response.raise_for_status()
        lines = response.text.splitlines()
        print(f"OK - {len(lines)} lines, HTTP {response.status_code}", flush=True)
        print("--- First 10 lines ---", flush=True)
        for l in lines[:10]:
            print(repr(l), flush=True)
        print("----------------------", flush=True)
    except Exception as e:
        print(f"Fetch Error: {e}", flush=True)
        return

    raw_channels = []
    current_key_url = ""
    current_logo = ""
    current_name = ""

    # List of generic names to filter out
    UNNECESSARY_NAMES = {
        'live', 'hls', 'api', 'smil', 'ngrp', 'streams', 'stream',
        'master', 'index', 'fhd', 'sdp', 'chunklist', 'playlist'
    }

    def is_hex(s):
        try:
            int(s, 16)
            return len(s) > 8
        except ValueError:
            return False

    def is_uuid(s):
        return bool(re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', s.lower()))

    for line in lines:
        line = line.strip()
        if not line: continue

        if line.startswith("#EXTINF"):
            logo_match = re.search(r'tvg-logo="([^"]+)"', line)
            current_logo = logo_match.group(1) if logo_match else ""

            group_match = re.search(r'group-title="([^"]+)"', line)
            current_group = group_match.group(1) if group_match else "Unknown"

            name_match = re.search(r'tvg-name="([^"]+)"', line)
            tvg_name = name_match.group(1) if name_match else ""

            comma_parts = line.split(',')
            comma_name = comma_parts[-1].strip() if comma_parts else ""

            current_name = tvg_name if tvg_name else comma_name
            current_name = current_name.replace('_', ' ').replace('-', ' ').strip()

            if current_name.isupper() or current_name.islower():
                current_name = current_name.title()
                for acronym in ['Tv', 'Hd', 'Sd', 'Fhd', '4K']:
                    current_name = re.sub(rf'\b{acronym}\b', acronym.upper(), current_name, flags=re.IGNORECASE)

        if "inputstream.adaptive.license_key=" in line:
            current_key_url = line.split("=", 1)[-1]
        elif line.startswith("https://") or line.startswith("http://"):
            parts = line.split("|")
            stream_url = parts[0]
            cookie = ""
            if len(parts) > 1:
                p1 = parts[1].strip()
                if p1.lower().startswith("cookie="):
                    cookie = p1.split("=", 1)[-1].strip()
                else:
                    cookie = p1

            if not cookie and "__hdnea__=" in stream_url:
                hd_match = re.search(r"__hdnea__=([^&|\s]+)", stream_url)
                if hd_match:
                    cookie = f"__hdnea__={hd_match.group(1)}"

            final_name = current_name
            if not final_name or final_name.lower() in UNNECESSARY_NAMES:
                url_match = re.search(r'/bpk-tv/([^/]+)/', stream_url)
                final_name = url_match.group(1) if url_match else stream_url.split('/')[-2]

            clean_name = final_name.lower().strip()
            if (clean_name not in UNNECESSARY_NAMES and
                not is_hex(clean_name.replace('.sdp', '').replace('.m3u8', '')) and
                not is_uuid(clean_name)):

                raw_channels.append({
                    "name": final_name,
                    "url": stream_url,
                    "key_url": current_key_url,
                    "cookie": cookie,
                    "logo": current_logo,
                    "group": current_group
                })
            else:
                print(f"FILTERED OUT: '{final_name}' | clean='{clean_name}'", flush=True)

            current_key_url = ""
            current_logo = ""
            current_name = ""
            current_group = "Unknown"

    print(f"Found {len(raw_channels)} clean channels. Fetching keys...", flush=True)

    session = requests.Session()
    def process_channel(ch):
        kid, k, l_url = fetch_key(ch['key_url'], session, ch['cookie'])
        if not ch['key_url'].startswith("http") and ":" in ch['key_url']:
            parts = ch['key_url'].split(":")
            kid, k, l_url = parts[0], parts[1], ""

        return {
            "name": ch['name'],
            "url": ch['url'],
            "keyId": kid,
            "key": k,
            "licenseUrl": l_url,
            "cookie": ch['cookie'],
            "logo": ch['logo'],
            "group": ch['group']
        }

    with ThreadPoolExecutor(max_workers=10) as executor:
        channels = list(executor.map(process_channel, raw_channels))

    def sort_key(ch):
        name = ch['name'].lower()
        is_star_sports = 'star sports' in name
        priority = 0 if is_star_sports else 1
        return (priority, name)

    channels.sort(key=sort_key)

    print(f"Generating files...", flush=True)
    for ch in channels:
        safe_name = "".join([c if c.isalnum() or c in (' ', '_', '-') else '_' for c in ch['name']])
        safe_name = safe_name.replace(' ', '_')
        ch['fileName'] = f"{safe_name}.html"

        file_path = os.path.join(OUTPUT_DIR, ch['fileName'])
        content = HTML_TEMPLATE.replace("{CHANNEL_TITLE}", ch['name']) \
                               .replace("{STREAM_URL}", ch['url']) \
                               .replace("{KEY_ID}", ch['keyId'] or "") \
                               .replace("{KEY}", ch['key'] or "") \
                               .replace("{LICENSE_URL}", ch['licenseUrl'] or "") \
                               .replace("{COOKIE}", ch['cookie'] or "") \
                               .replace("{LOGO_URL}", ch['logo'] or "")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

    with open(os.path.join(OUTPUT_DIR, "channels.json"), "w", encoding="utf-8") as f:
        json.dump(channels, f, indent=2)
    print(f"Done! Generated {len(channels)} files.", flush=True)

if __name__ == "__main__":
    generate()

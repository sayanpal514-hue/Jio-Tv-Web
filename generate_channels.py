import os
import re
import requests
import json
import base64
from concurrent.futures import ThreadPoolExecutor

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
                except:
                    pass
        except Exception:
            if i == retries - 1:
                pass
    return "", "", url

def m3u_to_json(m3u_url, output_file="channels.json"):
    print(f"Fetching M3U from {m3u_url}...", flush=True)
    
    try:
        response = requests.get(m3u_url, timeout=30)
        response.raise_for_status()
        lines = response.text.splitlines()
        print(f"OK - {len(lines)} lines, HTTP {response.status_code}", flush=True)
    except Exception as e:
        print(f"Fetch Error: {e}", flush=True)
        return None

    raw_channels = []
    current_key_url = ""
    current_logo = ""
    current_name = ""
    current_group = "Unknown"

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
        if not line:
            continue

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

    # Create structured JSON data
    json_data = {
        "total": len(channels),
        "channels": channels
    }

    # Save to file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    
    print(f"Done! Generated {len(channels)} channels in {output_file}", flush=True)
    return json_data

if __name__ == "__main__":
    M3U_URL = "https://raw.githubusercontent.com/opensourceflix/Friday/refs/heads/main/tmp/%25/privates.m3u8"
    json_data = m3u_to_json(M3U_URL, "sports.json")
    
    # Print sample output
    if json_data:
        print("\nSample output:")
        print(json.dumps(json_data["channels"][:2], indent=2, ensure_ascii=False))

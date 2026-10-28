"""
Relaie les actualités officielles AION 2 (flux Steam, en français) vers un salon Discord via webhook.
Lancé par GitHub Actions toutes les 30 min. Anti-doublon via cache/steam_seen.json.
"""
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

import requests

FEED_URL = os.getenv("STEAM_FEED_URL", "https://store.steampowered.com/feeds/news/app/3393110/?cc=FR&l=french")
WEBHOOK = os.getenv("DISCORD_WEBHOOK_NEWS", "").strip()
MENTION = os.getenv("DISCORD_MENTION_NEWS", "").strip()
SEEN_PATH = os.path.join("cache", "steam_seen.json")
MAX_PER_RUN = 3            # garde-fou anti-spam


def load_seen():
    try:
        with open(SEEN_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_seen(seen):
    os.makedirs(os.path.dirname(SEEN_PATH), exist_ok=True)
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(seen[-200:], f)


def clean_html(raw, limit=1500):
    text = re.sub(r"<br\s*/?>", "\n", raw or "", flags=re.I)
    text = re.sub(r"</p>|</li>|</h\d>", "\n", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "• ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\[/?[a-zA-Z_*]+[^\]]*\]", "", text)  # balises Steam type [carousel]
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def fetch_items():
    r = requests.get(FEED_URL, timeout=20, headers={"User-Agent": "BTP-AION2-news/1.0"})
    r.raise_for_status()
    root = ET.fromstring(r.content)
    items = []
    for it in root.iter("item"):
        guid = (it.findtext("guid") or it.findtext("link") or "").strip()
        title = html.unescape((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        desc = it.findtext("description") or ""
        pub = it.findtext("pubDate") or ""
        try:
            dt = parsedate_to_datetime(pub)
        except Exception:
            dt = datetime.now(timezone.utc)
        img = None
        m = re.search(r'<img[^>]+src="([^"]+)"', desc)
        if m:
            img = m.group(1)
        items.append({"id": guid, "title": title, "link": link, "desc": clean_html(desc), "dt": dt, "img": img})
    items.sort(key=lambda x: x["dt"])  # plus ancien -> plus récent
    return items


def color_for(title):
    t = title.lower()
    if "notes de version" in t or "patch" in t or "mise à jour" in t:
        return 0x2ECC71  # vert : patch notes
    if "maintenance" in t:
        return 0xE67E22  # orange
    return 0x3498DB      # bleu : annonce


def post(item):
    is_patch = color_for(item["title"]) == 0x2ECC71
    embed = {
        "title": item["title"][:256],
        "url": item["link"],
        "description": item["desc"] or "(voir le lien)",
        "color": color_for(item["title"]),
        "footer": {"text": "Source : Steam • AION 2 officiel • BTP"},
        "timestamp": item["dt"].astimezone(timezone.utc).isoformat(),
    }
    if item.get("img"):
        embed["image"] = {"url": item["img"]}
    payload = {"username": "Actus AION 2", "embeds": [embed]}
    content = ("📜 **Nouvelles notes de version AION 2**" if is_patch else "📰 **Actu officielle AION 2**")
    if MENTION:
        content = f"{MENTION} {content}"
    payload["content"] = content
    r = requests.post(WEBHOOK, json=payload, timeout=15)
    if r.status_code not in (200, 204):
        print(f"[news] Erreur Discord {r.status_code}: {r.text}")
        return False
    print(f"[news] Posté : {item['title']}")
    return True


def main():
    test = "--test" in sys.argv
    if not WEBHOOK:
        print("[news] DISCORD_WEBHOOK_NEWS manquant")
        return 1
    items = fetch_items()
    if not items:
        print("[news] Flux vide")
        return 0
    seen = load_seen()
    if test:
        post(items[-1])
        return 0
    first_run = seen is None
    seen = seen or []
    if first_run:
        # premier lancement : on mémorise l'existant sans rien reposter (le test a déjà posté la dernière)
        new = []
        seen = [i["id"] for i in items]
    else:
        new = [i for i in items if i["id"] not in seen][-MAX_PER_RUN:]
    for it in new:
        if post(it):
            seen.append(it["id"])
    if not new:
        print("[news] Rien de nouveau")
    save_seen(seen)
    return 0


if __name__ == "__main__":
    sys.exit(main())

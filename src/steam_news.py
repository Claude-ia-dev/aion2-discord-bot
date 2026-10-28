"""
Relaie les actus officielles AION 2 (site NC, version FR) vers Discord via webhook :
notes de version, mises à jour, maintenances et annonces.
Source : API publique du site officiel aion2.plaync.com (tableaux "Annonces" et "Mises à jour").
Lancé par GitHub Actions toutes les 15 min. Anti-doublon via cache/news_seen.json.
"""
import html
import json
import os
import re
import sys
from datetime import datetime, timezone

import requests

API = "https://api-global-community.plaync.com/aion2_global/board/{board}/article/search/moreArticle?isVote=true&moreSize=15&moreDirection=BEFORE&previousArticleId=0"
BOARDS = {
    "notice_fr": "https://aion2.plaync.com/fr-fr/board/notice/view?articleId={id}",
    "update_fr": "https://aion2.plaync.com/fr-fr/board/update/view?articleId={id}",
}
WEBHOOK = os.getenv("DISCORD_WEBHOOK_NEWS", "").strip()
MENTION_MAINT = os.getenv("DISCORD_MENTION_MAINTENANCE", "").strip()   # ex. @here (optionnel)
SEEN_PATH = os.path.join("cache", "news_seen.json")
MAX_PER_RUN = 5
SKIP = ("restrictions de compte",)   # listes de bans : pas utiles au serveur


def load_seen():
    try:
        with open(SEEN_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_seen(seen):
    os.makedirs(os.path.dirname(SEEN_PATH), exist_ok=True)
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(seen[-400:], f)


def clean(raw, limit=500):
    text = re.sub(r"<br\s*/?>", "\n", raw or "", flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"\[/?[a-zA-Z_*]+[^\]]*\]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def fetch_items():
    items = []
    for board, url_tpl in BOARDS.items():
        r = requests.get(API.format(board=board), timeout=20,
                         headers={"User-Agent": "Mozilla/5.0 BTP-AION2-news", "Accept": "application/json"})
        r.raise_for_status()
        for a in r.json().get("contentList", []):
            title = clean(a.get("title", ""), 256)
            if any(s in title.lower() for s in SKIP):
                continue
            ts = (a.get("timestamps") or {}).get("postedAt")
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                dt = datetime.now(timezone.utc)
            items.append({
                "id": a["id"], "board": board, "title": title,
                "link": url_tpl.format(id=a["id"]),
                "desc": clean(a.get("summary", "")),
                "img": a.get("thumbnailUrl"), "dt": dt,
            })
    items.sort(key=lambda x: x["dt"])
    return items


def kind(item):
    t = item["title"].lower()
    if "maintenance" in t:
        return "🛠️ **Maintenance AION 2**", 0xE67E22, True
    if item["board"] == "update_fr" or "notes de version" in t or "patch" in t:
        return "📜 **Notes de version AION 2**", 0x2ECC71, False
    if "mise à jour" in t:
        return "🔄 **Mise à jour AION 2**", 0x1ABC9C, False
    return "📰 **Annonce officielle AION 2**", 0x3498DB, False


def post(item):
    label, color, is_maint = kind(item)
    embed = {
        "title": item["title"],
        "url": item["link"],
        "description": (item["desc"] + "\n\n" if item["desc"] else "") + f"👉 [Lire en entier]({item['link']})",
        "color": color,
        "footer": {"text": "Source : site officiel AION 2 (NC) • BTP"},
        "timestamp": item["dt"].astimezone(timezone.utc).isoformat(),
    }
    if item.get("img"):
        embed["thumbnail"] = {"url": item["img"]}
    content = f"{MENTION_MAINT} {label}" if (is_maint and MENTION_MAINT) else label
    payload = {"username": "Actus AION 2", "content": content, "embeds": [embed]}
    r = requests.post(WEBHOOK, json=payload, timeout=15)
    if r.status_code not in (200, 204):
        print(f"[news] Erreur Discord {r.status_code}: {r.text}")
        return False
    print(f"[news] Posté : {item['title']}")
    return True


def main():
    if not WEBHOOK:
        print("[news] DISCORD_WEBHOOK_NEWS manquant")
        return 1
    items = fetch_items()
    print(f"[news] {len(items)} articles récupérés")
    if "--test" in sys.argv:
        # montre un exemple de chaque type : dernière maintenance + dernières notes de version
        maint = [i for i in items if "maintenance" in i["title"].lower()]
        notes = [i for i in items if i["board"] == "update_fr"]
        for it in (maint[-1:] + notes[-1:]):
            post(it)
        return 0
    seen = load_seen()
    if seen is None:
        # premier lancement : on mémorise l'existant sans rien reposter
        save_seen([i["id"] for i in items])
        print("[news] Premier lancement : historique mémorisé")
        return 0
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

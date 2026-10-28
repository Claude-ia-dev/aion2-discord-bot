import json
import requests
from datetime import datetime

import os

def build_discord_embed(event_info, attachment_filename=None):
    """
    Construit l'embed Discord (horaires dynamiques, miniature du boss, carte).
    """
    event = event_info["event"]
    spawn_time = event_info["spawn_time"]
    minutes_left = event_info.get("minutes_left", 10)
    unix_ts = int(spawn_time.timestamp())

    icon = event.get("icon", "⚔️")
    name = event.get("name", "Événement")
    category = event.get("category", "Événement")
    location = event.get("location", "Monde de jeu")
    map_url = event.get("map_url", "https://gamers4.life/aion-2/database/en/events/")
    color = event.get("color", 3718648)
    desc = event.get("description", "")

    embed = {
        "title": f"{icon} Dans ~{minutes_left} min : {name}",
        "url": map_url,
        "description": desc,
        "color": color,
        "fields": [
            {
                "name": "⏰ Début",
                "value": f"<t:{unix_ts}:t> (<t:{unix_ts}:R>)",
                "inline": True
            },
            {
                "name": "📍 Lieu",
                "value": location,
                "inline": True
            },
            {
                "name": "🏷️ Catégorie",
                "value": category,
                "inline": True
            }
        ],
        "footer": {
            "text": "Alertes AION 2 • BTP • Serveur EU Beritra",
            "icon_url": "https://gamers4.life/aion-2/database/aion2-logo.png"
        },
        "timestamp": datetime.utcnow().isoformat()
    }

    # Miniature du boss (avatar)
    if event.get("thumbnail_url"):
        embed["thumbnail"] = {"url": event["thumbnail_url"]}

    # Image de la carte (pièce jointe locale ou URL distante)
    if attachment_filename:
        embed["image"] = {"url": f"attachment://{attachment_filename}"}
    elif event.get("image_url"):
        embed["image"] = {"url": event["image_url"]}

    if map_url and "interactivemap.app" in map_url:
        embed["fields"].append({
            "name": "🗺️ Carte interactive",
            "value": f"[Clique ici pour ouvrir la carte]({map_url})",
            "inline": False
        })

    return embed

def send_discord_notification(webhook_url, event_info, mention=""):
    """
    Envoie la notification à Discord via webhook (pièces jointes supportées).
    """
    if not webhook_url or "discord.com/api/webhooks" not in webhook_url:
        print(f"[Notifier - Console/DryRun] Notification pour {event_info['event']['name']} (dans ~{event_info.get('minutes_left')} min)")
        return True

    event_id = event_info["event"].get("id", "")
    local_map = os.path.join("assets", "maps", f"{event_id}.png")
    
    attachment_name = None
    file_handle = None

    if os.path.exists(local_map):
        attachment_name = f"{event_id}.png"

    embed = build_discord_embed(event_info, attachment_filename=attachment_name)
    payload = {
        "username": "Alertes AION 2",
        "avatar_url": "https://gamers4.life/aion-2/database/aion2-logo.png",
        "embeds": [embed]
    }

    if mention:
        payload["content"] = mention

    try:
        if attachment_name and os.path.exists(local_map):
            with open(local_map, "rb") as f:
                files = {
                    "files[0]": (attachment_name, f, "image/png")
                }
                response = requests.post(
                    webhook_url,
                    data={"payload_json": json.dumps(payload)},
                    files=files,
                    timeout=15
                )
        else:
            response = requests.post(
                webhook_url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=10
            )

        if response.status_code in [200, 204]:
            print(f"[Notifier] Notification envoyée sur Discord pour {event_info['event']['name']}!")
            return True
        else:
            print(f"[Notifier Erreur] Status {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"[Notifier Exception] Erreur de connexion à Discord: {e}")
        return False

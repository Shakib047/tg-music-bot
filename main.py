import os
import requests
from fastapi import FastAPI, Request

app = FastAPI()

# ============ CONFIG ============
BOT_TOKEN = os.getenv("BOT_TOKEN")
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
SAAVN_API = "https://jiosavan-api2.vercel.app/api/search/songs"

ADMIN_ID = 6607731077  # sakib sir admin ID

# ============ STORAGE ============
USER_CACHE = {}        # {chat_id: [songs]}
USER_SET = set()       # unique users
TOTAL_SEARCH = 0       # total searches
# ================================


# ============ HELPERS ============
def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(f"{TG_API}/sendMessage", json=payload, timeout=10)


def send_audio(chat_id, url, title, artist):
    payload = {
        "chat_id": chat_id,
        "audio": url,
        "title": title,
        "performer": artist,
        "caption": f"🎵 <b>{title}</b>\n🎤 {artist}\n🎧 HQ Audio (320kbps)",
        "parse_mode": "HTML"
    }
    requests.post(f"{TG_API}/sendAudio", data=payload, timeout=30)


def search_songs(query):
    r = requests.get(
        SAAVN_API,
        params={"query": query, "limit": 10},
        timeout=10
    )
    data = r.json()
    results = []

    for song in data.get("data", {}).get("results", []):
        dls = song.get("downloadUrl", [])

        # 320kbps priority
        url = next((d["url"] for d in dls if d.get("quality") == "320kbps"), None)
        if not url and dls:
            url = dls[-1]["url"]

        if not url:
            continue

        artists = song.get("artists", {}).get("primary", [])
        artist = ", ".join(a["name"] for a in artists) if artists else "Unknown"

        results.append({
            "title": song.get("name", "Unknown"),
            "artist": artist,
            "url": url
        })

    return results


def build_buttons(songs):
    keyboard = []
    for i, s in enumerate(songs):
        keyboard.append([
            {
                "text": f"🎧 {i+1}. {s['title']}",
                "callback_data": str(i)
            }
        ])
    return {"inline_keyboard": keyboard}
# ================================


@app.get("/")
async def root():
    return {"status": "ok", "message": "Telegram Music Bot is running 🎧"}


@app.post("/webhook")
async def webhook(req: Request):
    global TOTAL_SEARCH
    update = await req.json()

    # ---------- BUTTON CLICK ----------
    if "callback_query" in update:
        cb = update["callback_query"]
        chat_id = cb["message"]["chat"]["id"]
        idx = int(cb["data"])

        if chat_id not in USER_CACHE:
            return {"ok": True}

        songs = USER_CACHE[chat_id]
        if idx >= len(songs):
            return {"ok": True}

        song = songs[idx]
        send_audio(chat_id, song["url"], song["title"], song["artist"])
        return {"ok": True}

    # ---------- MESSAGE ----------
    msg = update.get("message")
    if not msg or "text" not in msg:
        return {"ok": True}

    chat_id = msg["chat"]["id"]
    text = msg["text"].strip()

    # register user
    USER_SET.add(chat_id)

    # /start
    if text == "/start":
        send_message(
            chat_id,
            "👋 <b>Welcome to Music Bot</b>\n\n"
            "🎧 <b>যেকোনো গান নাম লিখুন</b>\n"
            "<i>tum hi ho</i>\n\n"
            "⬇️ নিচের list থেকে গান বেছে নিন\n"
            "▶️ Telegram-এই play করুন বা download করুন"
        )
        return {"ok": True}

    # /stats (ADMIN ONLY)
    if text == "/stats":
        if chat_id != ADMIN_ID:
            send_message(chat_id, "❌ You are not allowed to use this command")
            return {"ok": True}

        send_message(
            chat_id,
            f"📊 <b>Bot Statistics</b>\n\n"
            f"👥 Total Users: <b>{len(USER_SET)}</b>\n"
            f"🎧 Total Searches: <b>{TOTAL_SEARCH}</b>"
        )
        return {"ok": True}

    # ignore other commands
    if text.startswith("/"):
        send_message(chat_id, "❌ শুধু গান নাম লিখুন (no command needed)")
        return {"ok": True}

    # ---------- AUTO SONG SEARCH ----------
    TOTAL_SEARCH += 1

    songs = search_songs(text)
    if not songs:
        send_message(chat_id, "😔 কোনো গান পাওয়া যায়নি")
        return {"ok": True}

    USER_CACHE[chat_id] = songs

    reply = "🎵 <b>Search Results:</b>\n\n"
    for i, s in enumerate(songs):
        reply += f"{i+1}. <b>{s['title']}</b>\n🎤 {s['artist']}\n\n"

    send_message(chat_id, reply, build_buttons(songs))
    return {"ok": True}

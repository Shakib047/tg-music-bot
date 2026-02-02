import os
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
SAAVN_API = "https://jiosavan-api2.vercel.app/api/search/songs"

USER_CACHE = {}  # {chat_id: {"songs": [...], "index": 0}}

# ================== HELPERS ==================

def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(f"{TG_API}/sendMessage", json=payload, timeout=10)


def send_mp3(chat_id, url, title, artist):
    payload = {
        "chat_id": chat_id,
        "document": url,
        "caption": f"🎵 <b>{title}</b>\n🎤 {artist}",
        "parse_mode": "HTML",
        "filename": f"{title}.mp3"
    }
    requests.post(f"{TG_API}/sendDocument", data=payload, timeout=30)


def search_songs(query):
    r = requests.get(SAAVN_API, params={"query": query, "limit": 5}, timeout=10)
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


def nav_buttons():
    return {
        "inline_keyboard": [[
            {"text": "⏮ Previous", "callback_data": "prev"},
            {"text": "⏭ Next", "callback_data": "next"}
        ]]
    }

# ================== ROUTES ==================

@app.get("/")
async def root():
    return {"status": "ok", "message": "Telegram Music Bot is running 🎧"}


@app.post("/webhook")
async def webhook(req: Request):
    update = await req.json()

    # ---------- CALLBACK ----------
    if "callback_query" in update:
        cb = update["callback_query"]
        chat_id = cb["message"]["chat"]["id"]
        action = cb["data"]

        if chat_id not in USER_CACHE:
            return {"ok": True}

        songs = USER_CACHE[chat_id]["songs"]
        idx = USER_CACHE[chat_id]["index"]

        if action == "next":
            idx = (idx + 1) % len(songs)
        elif action == "prev":
            idx = (idx - 1) % len(songs)
        else:
            return {"ok": True}

        USER_CACHE[chat_id]["index"] = idx
        song = songs[idx]

        send_mp3(chat_id, song["url"], song["title"], song["artist"])
        send_message(chat_id, "🔁 গান পরিবর্তন করুন:", nav_buttons())

        return {"ok": True}

    # ---------- MESSAGE ----------
    msg = update.get("message")
    if not msg or "text" not in msg:
        return {"ok": True}

    chat_id = msg["chat"]["id"]
    text = msg["text"]

    # /start command
    if text == "/start":
        send_message(
            chat_id,
            "👋 <b>Welcome to Music Bot</b>\n\n"
            "🎧 গান ডাউনলোড করতে লিখুন:\n"
            "<code>/song song name</code>\n\n"
            "📌 Example:\n"
            "<code>/song tum hi ho</code>\n\n"
            "⬅️➡️ Next / Previous দিয়ে গান বদলাতে পারবেন"
        )
        return {"ok": True}

    # /song command
    if text.startswith("/song"):
        query = text.replace("/song", "").strip()
        if not query:
            send_message(chat_id, "❌ Example:\n<code>/song tum hi ho</code>")
            return {"ok": True}

        songs = search_songs(query)
        if not songs:
            send_message(chat_id, "😔 কোনো গান পাওয়া যায়নি")
            return {"ok": True}

        USER_CACHE[chat_id] = {"songs": songs, "index": 0}
        first = songs[0]

        send_mp3(chat_id, first["url"], first["title"], first["artist"])
        send_message(chat_id, "🔁 গান পরিবর্তন করুন:", nav_buttons())

    return {"ok": True}

import os
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Vercel env variable
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
SAAVN_API = "https://jiosavan-api2.vercel.app/api/search/songs"

# Simple in-memory cache (free hosting friendly)
USER_CACHE = {}
# =========================================


def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    requests.post(f"{TG_API}/sendMessage", json=payload, timeout=10)


def send_audio(chat_id, audio_url, title, artist):
    payload = {
        "chat_id": chat_id,
        "audio": audio_url,
        "title": title,
        "performer": artist
    }
    requests.post(f"{TG_API}/sendAudio", data=payload, timeout=20)


def search_songs(query: str):
    r = requests.get(
        SAAVN_API,
        params={"query": query, "limit": 5},
        timeout=10
    )
    data = r.json()

    results = []

    for song in data.get("data", {}).get("results", []):
        download_urls = song.get("downloadUrl", [])

        # 🔥 Auto 320kbps priority
        audio_url = next(
            (d["url"] for d in download_urls if d.get("quality") == "320kbps"),
            None
        )

        # fallback
        if not audio_url and download_urls:
            audio_url = download_urls[-1]["url"]

        if not audio_url:
            continue

        artists = song.get("artists", {}).get("primary", [])
        artist_name = ", ".join(a["name"] for a in artists) if artists else "Unknown"

        results.append({
            "title": song.get("name", "Unknown"),
            "artist": artist_name,
            "url": audio_url
        })

    return results


@app.get("/")
async def root():
    return {"status": "ok", "message": "Telegram Music Bot is running 🎧"}


@app.post("/webhook")
async def telegram_webhook(request: Request):
    update = await request.json()

    # ================= CALLBACK BUTTON =================
    if "callback_query" in update:
        cb = update["callback_query"]
        chat_id = cb["message"]["chat"]["id"]
        data = cb["data"]

        if chat_id in USER_CACHE:
            song = USER_CACHE[chat_id][int(data)]
            send_audio(
                chat_id,
                song["url"],
                song["title"],
                song["artist"]
            )

        return JSONResponse(content={"ok": True})

    # ================= NORMAL MESSAGE =================
    message = update.get("message")
    if not message or "text" not in message:
        return JSONResponse(content={"ok": True})

    chat_id = message["chat"]["id"]
    text = message["text"]

    if text.startswith("/song"):
        query = text.replace("/song", "").strip()

        if not query:
            send_message(chat_id, "❌ গান নাম লিখুন\nExample: <code>/song tum hi ho</code>")
            return JSONResponse(content={"ok": True})

        songs = search_songs(query)

        if not songs:
            send_message(chat_id, "😔 কোনো গান পাওয়া যায়নি")
            return JSONResponse(content={"ok": True})

        USER_CACHE[chat_id] = songs

        reply_text = "🎵 <b>গানগুলো বেছে নিন / Select a song:</b>\n\n"
        buttons = []

        for i, s in enumerate(songs):
            reply_text += f"{i+1}. <b>{s['title']}</b>\n🎤 {s['artist']}\n\n"
            buttons.append([
                {
                    "text": f"🎧 {i+1}",
                    "callback_data": str(i)
                }
            ])

        send_message(
            chat_id,
            reply_text,
            {"inline_keyboard": buttons}
        )

    return JSONResponse(content={"ok": True})

import logging
import os
import sqlite3
import threading
import time
from bs4 import BeautifulSoup
from flask import Flask
import feedparser
import requests
from urllib.parse import urljoin

app = Flask(__name__)

# =========================
# إعدادات البوت (ضع بياناتك هنا مباشرة)
# =========================
BOT_TOKEN = "8598395244:AAGtNGGIMnVdCulcQ-EQLeR9bMugMgDd43g"
CHANNEL_ID = "@Qissa_eshq"
RSS_URL = "https://qeseh.net/"

CHECK_INTERVAL = 600
DATABASE = "episodes.db"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

session = requests.Session()
session.headers.update({"User-Agent": "SeriesUpdateBot/1.0"})


@app.route("/")
def home():
  return "Qissa Eshq Bot is running 24/7!"


# =========================
# قاعدة البيانات
# =========================


def init_database():
  with sqlite3.connect(DATABASE) as conn:
    conn.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                url TEXT PRIMARY KEY,
                title TEXT,
                published_at TEXT
            )
        """)


def is_published(url):
  with sqlite3.connect(DATABASE) as conn:
    result = conn.execute(
        "SELECT 1 FROM episodes WHERE url = ?", (url,)
    ).fetchone()
  return result is not None


def save_episode(url, title):
  with sqlite3.connect(DATABASE) as conn:
    conn.execute(
        """
            INSERT OR IGNORE INTO episodes
            (url, title, published_at)
            VALUES (?, ?, datetime('now'))
            """,
        (url, title),
    )


# =========================
# إرسال رسائل تلجرام
# =========================


def telegram_request(method, data):
  if not BOT_TOKEN:
    raise RuntimeError("متغير BOT_TOKEN غير مضبوط")

  api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
  response = requests.post(api_url, data=data, timeout=30)
  response.raise_for_status()
  result = response.json()

  if not result.get("ok"):
    raise RuntimeError(result)
  return result


def publish_episode(title, description, url, image_url=None):
  message = (
      f"🎬 {title}\n\n📝 الوصف:\n{description or 'لا يوجد وصف'}\n\n▶️ رابط"
      f" المشاهدة:\n{url}"
  )

  if image_url:
    try:
      telegram_request(
          "sendPhoto",
          {
              "chat_id": CHANNEL_ID,
              "photo": image_url,
              "caption": message[:1024],
          },
      )
      return
    except Exception as error:
      logging.warning("تعذر إرسال الصورة: %s", error)

  telegram_request(
      "sendMessage",
      {
          "chat_id": CHANNEL_ID,
          "text": message,
          "disable_web_page_preview": False,
      },
  )


# =========================
# قراءة بيانات الموقع
# =========================


def fetch_episodes():
  if not RSS_URL:
    return []

  response = session.get(RSS_URL, timeout=30)
  response.raise_for_status()

  feed = feedparser.parse(response.content)
  episodes = []

  for entry in feed.entries:
    url = entry.get("link", "").strip()
    title = entry.get("title", "حلقة جديدة").strip()
    description = entry.get("summary", "").strip()
    image_url = None

    if not url:
      continue

    if description:
      soup = BeautifulSoup(description, "html.parser")
      image = soup.find("img")
      if image and image.get("src"):
        image_url = urljoin(url, image["src"])
      description = soup.get_text(" ", strip=True)

    episodes.append({
        "title": title,
        "description": description,
        "url": url,
        "image_url": image_url,
    })

  return episodes


# =========================
# المراقبة التلقائية
# =========================


def monitor():
  while True:
    try:
      logging.info("فحص الحلقات الجديدة...")
      episodes = fetch_episodes()

      for episode in reversed(episodes):
        url = episode["url"]
        if is_published(url):
          continue

        publish_episode(
            title=episode["title"],
            description=episode["description"],
            url=url,
            image_url=episode["image_url"],
        )
        save_episode(url, episode["title"])
        logging.info("تم نشر: %s", episode["title"])

    except Exception:
      logging.exception("حدث خطأ أثناء المراقبة")

    time.sleep(CHECK_INTERVAL)


# =========================
# تشغيل المشروع
# =========================

if __name__ == "__main__":
  if not BOT_TOKEN or not CHANNEL_ID:
    raise SystemExit("يرجى ضبط BOT_TOKEN و CHANNEL_ID")

  init_database()

  # تشغيل فحص الحلقات في الخلفية
  t = threading.Thread(target=monitor)
  t.daemon = True
  t.start()

  # تشغيل سيرفر الويب لكي يستجيب Render ويفتح المنفذ
  port = int(os.environ.get("PORT", 10000))
  app.run(host="0.0.0.0", port=port)

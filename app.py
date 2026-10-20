import logging
import os
import sqlite3
import threading
import time
from bs4 import BeautifulSoup
from flask import Flask
import requests
from urllib.parse import urljoin

app = Flask(__name__)

# =========================
# إعدادات البوت
# =========================
BOT_TOKEN = "8598395244:AAGtNGGIMnVdCulcQ-EQLeR9bMugMgDd43g "
CHANNEL_ID = "@Qissa_eshq"
TARGET_URL = "https://qeseh.net/"

CHECK_INTERVAL = 600  # فحص كل 10 دقائق
DATABASE = "episodes.db"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
})


@app.route("/")
def home():
  return "Qissa Eshq Bot is running and monitoring!"


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


def is_db_empty():
  with sqlite3.connect(DATABASE) as conn:
    count = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
  return count == 0


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
# قراءة بيانات الموقع مباشرة
# =========================


def fetch_episodes():
  if not TARGET_URL:
    return []

  response = session.get(TARGET_URL, timeout=30)
  response.raise_for_status()

  soup = BeautifulSoup(response.text, "html.parser")
  episodes = []

  # استخراج الروابط من الموقع (البحث عن الروابط التي قد تمثل حلقات أو مسلسلات)
  for a in soup.find_all("a", href=True):
    url = a["href"].strip()
    title = a.get_text(strip=True)

    # فلترة الروابط لتكون مقبولة وليست روابط فارغة أو عامة جداً
    if url and title and len(title) > 4:
      full_url = urljoin(TARGET_URL, url)

      # تجنب التكرار داخل نفس القائمة المستخرجة
      if not any(ep["url"] == full_url for ep in episodes):
        episodes.append({
            "title": title,
            "description": "حلقة جديدة متاحة الآن على موقع قصة عشق.",
            "url": full_url,
            "image_url": None,
        })

  return episodes


# =========================
# المراقبة التلقائية
# =========================


def monitor():
  first_run = is_db_empty()

  while True:
    try:
      logging.info("فحص الحلقات الجديدة من الموقع...")
      episodes = fetch_episodes()

      for episode in reversed(episodes):
        url = episode["url"]

        if is_published(url):
          continue

        # إذا كانت التشغيلة الأولى، نقوم بحفظ الحلقات القديمة بصمت دون إرسالها لعدم إزعاج القناة
        if first_run:
          save_episode(url, episode["title"])
          continue

        # النشر في القناة إذا كانت حلقة جديدة حقاً بعد التشغيلة الأولى
        publish_episode(
            title=episode["title"],
            description=episode["description"],
            url=url,
            image_url=episode["image_url"],
        )
        save_episode(url, episode["title"])
        logging.info("تم نشر حلقة جديدة: %s", episode["title"])

      if first_run:
        logging.info(
            "تمت أرشفة الحلقات القديمة بنجاح. سيتم الآن مراقبة أي جديد."
        )
        first_run = False

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

  # تشغيل سيرفر الويب لكي يستجيب Render
  port = int(os.environ.get("PORT", 10000))
  app.run(host="0.0.0.0", port=port)
 

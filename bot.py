#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MangaBuff bot — FULL COMBO
MODE=all | FREE_PROXIES | DDoS errors → Telegram
CLUB_SLUG чистится, если вставили полный URL
"""

from __future__ import annotations

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MangaBuff bot для Termux
При любой аварии пишет в Telegram:
«Извините пожалуйста, но я обосрался» + где + про унитаз
"""

from __future__ import annotations

import os
import re
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as cffi_requests
    HAS_CFFI = True
except Exception:
    HAS_CFFI = False

try:
    import cloudscraper
    HAS_CS = True
except Exception:
    HAS_CS = False

# ===================== загрузка config.env =====================
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.env"


def load_config() -> None:
    if not CONFIG_PATH.exists():
        return
    for line in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


load_config()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()
FULL_COOKIE = os.environ.get("FULL_COOKIE", "").strip()
MODE = os.environ.get("MODE", "all").strip().lower()

_raw_slug = os.environ.get("CLUB_SLUG", "utinoe-bratstvo").strip().rstrip("/")
if "mangabuff.ru" in _raw_slug or "/" in _raw_slug:
    m = re.search(r"clubs/([^/?#]+)", _raw_slug)
    CLUB_SLUG = m.group(1) if m else _raw_slug.split("/")[-1]
else:
    CLUB_SLUG = _raw_slug or "utinoe-bratstvo"

BASE = "https://mangabuff.ru"
BOOST_URL = f"{BASE}/clubs/{CLUB_SLUG}/boost"
HISTORY_URL = f"{BASE}/clubs/{CLUB_SLUG}/history"
CLUB_NAME = "Утиное Братство"
MSK = ZoneInfo("Europe/Moscow")

UA_LIST = [
    "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

BAD_WORDS = (
    "замен", "опыт", "сегодня", "доступно", "карт", "штраф", "бесплат", "платн",
    "неделя", "сутки", "месяц", "правил", "клуб", "boost", "history", "войти", "регистр",
)


def now_msk() -> str:
    return datetime.now(MSK).strftime("%d.%m.%Y, %H:%M МСК")


def send_telegram(text: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        print("Нет BOT_TOKEN или CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": text[:4000],
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=30,
        )
        if not r.ok:
            print(f"Telegram error: {r.status_code} {r.text[:300]}")
    except Exception as e:
        print(f"Telegram fail: {e}")


def die(where: str, detail: str = "", code: int = 1) -> None:
    """
    Единый «я обосрался» + где сломался + фирменная фраза
    """
    detail = (detail or "").strip()
    msg = (
        "Извините пожалуйста, но я <b>обосрался</b> 💩\n"
        f"<b>Где:</b> <code>{where}</code>\n"
    )
    if detail:
        msg += f"<b>Что случилось:</b>\n<code>{detail[:2800]}</code>\n"
    msg += (
        "\n<i>Я головой бился об крышу унитаза вместо того, "
        "чтобы работать как надо.</i>\n"
        f"<i>{now_msk()}</i>"
    )
    print(f"DIE [{where}] {detail}", file=sys.stderr)
    send_telegram(msg)
    raise SystemExit(code)


def xsrf_from_cookie() -> Optional[str]:
    if not FULL_COOKIE:
        return None
    m = re.search(r"(?:^|;\s*)XSRF-TOKEN=([^;]+)", FULL_COOKIE)
    if not m:
        return None
    return unquote(m.group(1))


def base_headers(ua: str) -> dict:
    h = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
        "Referer": BOOST_URL,
        "Origin": BASE,
        "Cookie": FULL_COOKIE,
    }
    xsrf = xsrf_from_cookie()
    if xsrf:
        h["X-XSRF-TOKEN"] = xsrf
        h["X-Requested-With"] = "XMLHttpRequest"
    return h


def check_error(status: int, text: str, final_url: str) -> Optional[str]:
    head = (text or "")[:1500].lower()
    if status == 403 or "ddos-guard" in head or "ddos guard" in head:
        return "DDoS-Guard 403 (защита сайта)"
    if status == 429:
        return "429 Too Many Requests"
    if status != 200:
        return f"HTTP {status}"
    if "/login" in (final_url or "") or ("login" in head and "войти" in head):
        return "Cookie мёртвый (ушёл на login)"
    if "challenge" in head or "captcha" in head:
        return "Challenge / CAPTCHA"
    return None


def fetch_cffi(url: str, ua: str) -> Tuple[int, str, str]:
    if not HAS_CFFI:
        raise RuntimeError("curl_cffi нет")
    r = cffi_requests.get(
        url, headers=base_headers(ua), timeout=45, allow_redirects=True, impersonate="chrome131"
    )
    return r.status_code, r.text or "", str(getattr(r, "url", url) or url)


def fetch_cloudscraper(url: str, ua: str) -> Tuple[int, str, str]:
    if not HAS_CS:
        raise RuntimeError("cloudscraper нет")
    s = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "android", "mobile": True}
    )
    r = s.get(url, headers=base_headers(ua), timeout=45, allow_redirects=True)
    return r.status_code, r.text or "", str(getattr(r, "url", url) or url)


def fetch_requests(url: str, ua: str) -> Tuple[int, str, str]:
    r = requests.get(url, headers=base_headers(ua), timeout=45, allow_redirects=True)
    return r.status_code, r.text or "", str(getattr(r, "url", url) or url)


ENGINES = []
if HAS_CFFI:
    ENGINES.append(("curl_cffi", fetch_cffi))
if HAS_CS:
    ENGINES.append(("cloudscraper", fetch_cloudscraper))
ENGINES.append(("requests", fetch_requests))


def smart_fetch(url: str, where: str) -> str:
    errors: List[str] = []
    for name, engine in ENGINES:
        for ua in UA_LIST:
            try:
                print(f"[try] {name} {url}")
                status, text, final = engine(url, ua)
                err = check_error(status, text, final)
                if err:
                    errors.append(f"{name}: {err}")
                    time.sleep(0.3)
                    continue
                print(f"OK {name} len={len(text)}")
                return text
            except Exception as e:
                errors.append(f"{name}: {type(e).__name__}: {e}")
                time.sleep(0.2)
    die(
        where,
        "Не смог открыть страницу.\n"
        f"url={url}\n"
        f"cookie_len={len(FULL_COOKIE)}\n"
        + "\n".join(errors[-10:]),
    )
    return ""  # unreachable


def parse_boost_top(html: str, limit: int = 15) -> List[Tuple[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    out: List[Tuple[str, str]] = []
    seen = set()
    for el in soup.select(
        "a[href*='/users/'], li, tr, [class*='member'], [class*='boost'], "
        "[class*='top'], [class*='rating'], [class*='contrib']"
    ):
        text = " ".join(el.get_text(" ", strip=True).split())
        if not text or len(text) > 90:
            continue
        m = re.search(r"^(.+?)\s+(\d{1,7})$", text)
        if not m:
            continue
        name, score = m.group(1).strip(), m.group(2)
        low = name.lower()
        if any(b in low for b in BAD_WORDS) or name in seen or name.isdigit():
            continue
        if not re.search(r"[A-Za-zА-Яа-я]", name):
            continue
        seen.add(name)
        out.append((name, score))
        if len(out) >= limit:
            break
    return out


def parse_history(html: str, limit: int = 10) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    out: List[str] = []
    seen = set()
    for el in soup.select("li, tr, [class*='history'], [class*='log'], [class*='contrib']"):
        t = " ".join(el.get_text(" ", strip=True).split())
        if not (8 < len(t) < 140) or t in seen:
            continue
        if "ddos" in t.lower() or "cookie" in t.lower():
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= limit:
            break
    return out


def format_top(title: str, rows: List[Tuple[str, str]]) -> str:
    medals = ["🥇", "🥈", "🥉"]
    lines = [f"<b>{title}</b>", f"<i>{now_msk()}</i>", f"Клуб: <b>{CLUB_NAME}</b>", ""]
    if not rows:
        lines.append("⚠️ Топ пустой — возможно, вёрстка сайта изменилась")
    else:
        for i, (name, score) in enumerate(rows):
            p = medals[i] if i < 3 else f"{i + 1}."
            lines.append(f"{p} <b>{name}</b> — {score}")
    return "\n".join(lines)


def format_history(items: List[str]) -> str:
    lines = ["<b>📜 Последние вклады</b>", f"<i>{now_msk()}</i>", f"Клуб: <b>{CLUB_NAME}</b>", ""]
    if not items:
        lines.append("⚠️ История пустая / не распарсилась")
    else:
        for i, t in enumerate(items, 1):
            lines.append(f"{i}. {t}")
    return "\n".join(lines)


def main() -> int:
    print("=" * 50)
    print("MODE", MODE)
    print("CLUB", CLUB_SLUG)
    print("BOOST", BOOST_URL)
    print("cookie_len", len(FULL_COOKIE))
    print("engines", [n for n, _ in ENGINES])
    print("=" * 50)

    if not BOT_TOKEN or not CHAT_ID:
        die("старт / конфиг", "Нет BOT_TOKEN или CHAT_ID в config.env")

    if not FULL_COOKIE or len(FULL_COOKIE) < 40:
        die("старт / cookie", "FULL_COOKIE пустой или короткий — обнови config.env")

    try:
        if MODE in ("daily", "weekly", "all"):
            html = smart_fetch(BOOST_URL, "загрузка /boost")
            rows = parse_boost_top(html)
            if not rows:
                # не всегда фатально — но предупредим
                send_telegram(
                    "Извините пожалуйста, но я <b>частично обосрался</b> 💩\n"
                    "<b>Где:</b> <code>парсинг /boost</code>\n"
                    "Страницу открыл, а топ не нашёл.\n"
                    "<i>Я головой бился об крышу унитаза вместо того, чтобы работать как надо.</i>"
                )
            title = {
                "daily": "📊 Топ за сутки (boost)",
                "weekly": "📊 Топ за неделю (boost)",
                "all": "📊 Топ (boost)",
            }.get(MODE, "📊 Топ (boost)")
            send_telegram(format_top(title, rows))
            print("top:", len(rows))

        if MODE in ("recent", "all"):
            html = smart_fetch(HISTORY_URL, "загрузка /history")
            items = parse_history(html)
            if not items:
                send_telegram(
                    "Извините пожалуйста, но я <b>частично обосрался</b> 💩\n"
                    "<b>Где:</b> <code>парсинг /history</code>\n"
                    "Страницу открыл, а список вкладов не нашёл.\n"
                    "<i>Я головой бился об крышу унитаза вместо того, чтобы работать как надо.</i>"
                )
            send_telegram(format_history(items))
            print("history:", len(items))

        if MODE not in ("daily", "weekly", "recent", "all"):
            die("режим MODE", f"Неизвестный MODE={MODE}")

        return 0

    except SystemExit:
        raise
    except Exception as e:
        die(
            "неожиданный краш",
            f"{type(e).__name__}: {e}\n\n{traceback.format_exc()[-2000:]}",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

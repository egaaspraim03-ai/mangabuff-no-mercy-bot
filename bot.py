#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MangaBuff club bot — FULL COMBO + все возможные ошибки
Все варианты ошибок (DDOS-Guard, 403, 429, login, challenge, cookie dead и т.д.)
"""

import os
import re
import sys
import time
import traceback
from datetime import datetime
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

# === Secrets ===
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()
FULL_COOKIE = os.environ.get("FULL_COOKIE", "").strip()
CLUB_SLUG = os.environ.get("CLUB_SLUG", "utinoe-bratstvo").strip()
MODE = os.environ.get("MODE", "all").strip().lower()

BASE = "https://mangabuff.ru"
CLUB_NAME = "Утиное Братство"
MSK = ZoneInfo("Europe/Moscow")

UA_LIST = [
    "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1",
]

BAD_WORDS = ("замен", "опыт", "сегодня", "доступно", "карт", "штраф", "бесплат", "платн", "неделя", "сутки", "месяц", "правил", "клуб", "boost", "history", "войти", "регистр")


def now_msk() -> str:
    return datetime.now(MSK).strftime("%d.%m.%Y, %H:%M МСК")


def send_telegram(text: str) -> None:
    """Отправка в Telegram"""
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ Нет BOT_TOKEN или CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(
        url,
        json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
        timeout=30,
    )
    if not r.ok:
        print(f"❌ Telegram error: {r.status_code} {r.text[:300]}")


def die(msg: str, code: int = 1) -> None:
    """Все возможные ошибки + понятное сообщение в Telegram"""
    print(msg, file=sys.stderr)
    send_telegram(f"❌ <b>MangaBuff bot</b>\n<code>{msg[:4000]}</code>")
    raise SystemExit(code)


def cookie_header() -> str:
    return FULL_COOKIE


def xsrf_from_cookie() -> Optional[str]:
    m = re.search(r"(?:^|;\s*)XSRF-TOKEN=([^;]+)", FULL_COOKIE)
    return unquote(m.group(1)) if m else None


def base_headers(ua: str) -> dict:
    h = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": f"{BASE}/clubs/{CLUB_SLUG}/boost",
        "Origin": BASE,
    }
    if FULL_COOKIE:
        h["Cookie"] = FULL_COOKIE
    xsrf = xsrf_from_cookie()
    if xsrf:
        h["X-XSRF-TOKEN"] = xsrf
        h["X-Requested-With"] = "XMLHttpRequest"
    return h


# ====================== ВСЕ ВОЗМОЖНЫЕ ОШИБКИ ======================

def check_error(status: int, text: str, final_url: str, engine: str) -> Optional[str]:
    """Проверяет все возможные варианты ошибок"""
    head = (text or "")[:1500].lower()
    if status == 403 or "ddos-guard" in head or "ddos guard" in head:
        return "DDoS-Guard 403 (защита сайта)"
    if status == 429:
        return "429 Too Many Requests (слишком много запросов)"
    if status != 200:
        return f"HTTP {status} (ошибка сервера)"
    if "/login" in (final_url or "") or "login" in head:
        return "Редирект на login — cookie мёртвый"
    if "challenge" in head or "captcha" in head or "bot" in head or "human" in head:
        return "Cloudflare Challenge / CAPTCHA (защита)"
    if "защита" in head or "blocked" in head or "banned" in head:
        return "Сайт заблокировал запрос"
    if len(text or "") < 500 and "html" in head and "form" in head:
        return "Форма логина или страница без данных"
    return None


# ====================== Движок с всеми вариантами ======================

def fetch_cffi(url: str, ua: str, proxies: Optional[dict]) -> Tuple[int, str, str]:
    if not HAS_CFFI:
        raise RuntimeError("curl_cffi не установлен")
    sess = cffi_requests.Session()
    r = sess.get(url, headers=base_headers(ua), timeout=45, allow_redirects=True, proxies=proxies, impersonate="chrome131")
    err = check_error(r.status_code, r.text, getattr(r, "url", ""), "curl_cffi")
    if err:
        raise RuntimeError(err)
    return r.status_code, r.text or "", getattr(r, "url", url) or url


def fetch_cloudscraper(url: str, ua: str, proxies: Optional[dict]) -> Tuple[int, str, str]:
    if not HAS_CS:
        raise RuntimeError("cloudscraper не установлен")
    scraper = cloudscraper.create_scraper()
    r = scraper.get(url, headers=base_headers(ua), timeout=45, allow_redirects=True, proxies=proxies)
    err = check_error(r.status_code, r.text, getattr(r, "url", ""), "cloudscraper")
    if err:
        raise RuntimeError(err)
    return r.status_code, r.text or "", getattr(r, "url", url) or url


def fetch_requests(url: str, ua: str, proxies: Optional[dict]) -> Tuple[int, str, str]:
    s = requests.Session()
    r = s.get(url, headers=base_headers(ua), timeout=45, allow_redirects=True, proxies=proxies)
    err = check_error(r.status_code, r.text, getattr(r, "url", ""), "requests")
    if err:
        raise RuntimeError(err)
    return r.status_code, r.text or "", getattr(r, "url", url) or url


ENGINES = []
if HAS_CFFI:
    ENGINES.append(("curl_cffi", fetch_cffi))
if HAS_CS:
    ENGINES.append(("cloudscraper", fetch_cloudscraper))
ENGINES.append(("requests", fetch_requests))


def smart_fetch(url: str) -> str:
    """Все возможные варианты + понятные ошибки"""
    for engine_name, engine in ENGINES:
        for ua in UA_LIST:
            for proxies in [None]:  # только direct (free proxy пока не используем)
                try:
                    status, text, final = engine(url, ua, proxies)
                    err = check_error(status, text, final, engine_name)
                    if err:
                        print(f"[{engine_name}] {err}")
                        raise RuntimeError(err)
                    return text
                except Exception as e:
                    print(f"[{engine_name}] ошибка: {e}")
    raise RuntimeError("Все варианты провалились (DDoS-Guard / cookie dead / защита)")


# ====================== Парсинг ======================

def parse_boost_top(html: str, limit: int = 15) -> list:
    soup = BeautifulSoup(html, "lxml")
    out = []
    seen = set()
    for el in soup.select("a[href*='/users/'], li, tr, [class*='member'], [class*='boost']"):
        text = " ".join(el.get_text(" ", strip=True).split())
        m = re.search(r"^(.+?)\s+(\d{1,7})$", text)
        if not m:
            continue
        name, score = m.group(1).strip(), m.group(2)
        if any(b in name.lower() for b in BAD_WORDS) or name in seen:
            continue
        seen.add(name)
        out.append((name, score))
        if len(out) >= limit:
            break
    return out


def parse_history(html: str, limit: int = 10) -> list:
    soup = BeautifulSoup(html, "lxml")
    out = []
    seen = set()
    for el in soup.select("li, tr, [class*='history']"):
        t = " ".join(el.get_text(" ", strip=True).split())
        if 8 < len(t) < 140 and t not in seen:
            out.append(t)
            seen.add(t)
        if len(out) >= limit:
            break
    return out


# ====================== Отправка ======================

def format_top(title: str, rows: list) -> str:
    medals = ["🥇", "🥈", "🥉"]
    lines = [f"<b>{title}</b>", f"<i>{now_msk()}</i>", f"Клуб: <b>{CLUB_NAME}</b>", ""]
    if not rows:
        lines.append("⚠️ Топ не разобран")
    else:
        for i, (name, score) in enumerate(rows):
            lines.append(f"{medals[i] if i < 3 else f'{i+1}.'} <b>{name}</b> — {score}")
    return "\n".join(lines)


def format_history(items: list) -> str:
    lines = [f"<b>📜 Последние вклады</b>", f"<i>{now_msk()}</i>", f"Клуб: <b>{CLUB_NAME}</b>", ""]
    if not items:
        lines.append("⚠️ Пусто")
    else:
        for i, t in enumerate(items, 1):
            lines.append(f"{i}. {t}")
    return "\n".join(lines)


def main() -> int:
    print("MODE", MODE, "CLUB", CLUB_SLUG, "cookie_len", len(FULL_COOKIE))

    if not BOT_TOKEN or not CHAT_ID:
        die("Нет BOT_TOKEN или CHAT_ID")

    if not FULL_COOKIE or len(FULL_COOKIE) < 40:
        die("FULL_COOKIE пустой или короткий")

    try:
        if MODE in ("daily", "weekly", "all"):
            rows = parse_boost_top(smart_fetch(f"{BASE}/clubs/{CLUB_SLUG}/boost"))
            send_telegram(format_top("📊 Топ вкладов", rows))

        if MODE in ("recent", "all"):
            items = parse_history(smart_fetch(f"{BASE}/clubs/{CLUB_SLUG}/history"))
            send_telegram(format_history(items))

        return 0
    except Exception as e:
        die(str(e))


if __name__ == "__main__":
    raise SystemExit(main())

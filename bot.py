#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MangaBuff bot — FULL COMBO
MODE=all | FREE_PROXIES | DDoS errors → Telegram
CLUB_SLUG чистится, если вставили полный URL
"""

from __future__ import annotations

import os
import re
import sys
import time
import traceback
from datetime import datetime
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

# ===================== ENV =====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()
FULL_COOKIE = os.environ.get("FULL_COOKIE", "").strip()
FREE_PROXIES = os.environ.get("FREE_PROXIES", "").strip()
MODE = os.environ.get("MODE", "all").strip().lower()  # daily | weekly | recent | all

# CLUB_SLUG — только slug, если случайно полный URL — чистим
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
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]

BAD_WORDS = (
    "замен", "опыт", "сегодня", "доступно", "карт", "штраф", "бесплат", "платн",
    "неделя", "сутки", "месяц", "правил", "клуб", "boost", "history", "войти", "регистр",
)


def now_msk() -> str:
    return datetime.now(MSK).strftime("%d.%m.%Y, %H:%M МСК")


def send_telegram(text: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ Нет BOT_TOKEN или CHAT_ID — в Telegram не отправлено")
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
            print(f"❌ Telegram error: {r.status_code} {r.text[:300]}")
    except Exception as e:
        print(f"❌ Telegram send failed: {e}")


def die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    send_telegram(f"❌ <b>MangaBuff bot</b>\n<code>{msg[:3500]}</code>")
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
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": BOOST_URL,
        "Origin": BASE,
        "Upgrade-Insecure-Requests": "1",
    }
    if FULL_COOKIE:
        h["Cookie"] = FULL_COOKIE
    xsrf = xsrf_from_cookie()
    if xsrf:
        h["X-XSRF-TOKEN"] = xsrf
        h["X-Requested-With"] = "XMLHttpRequest"
    return h


def proxy_list() -> List[Optional[dict]]:
    out: List[Optional[dict]] = [None]  # сначала direct
    if not FREE_PROXIES:
        return out
    for p in FREE_PROXIES.split(","):
        p = p.strip()
        if not p:
            continue
        if not p.startswith("http"):
            p = "http://" + p
        out.append({"http": p, "https": p})
    return out


def check_error(status: int, text: str, final_url: str) -> Optional[str]:
    head = (text or "")[:1500].lower()
    if status == 403 or "ddos-guard" in head or "ddos guard" in head:
        return "DDoS-Guard 403 (защита сайта)"
    if status == 429:
        return "429 Too Many Requests"
    if status != 200:
        return f"HTTP {status}"
    if "/login" in (final_url or "") or ("login" in head and "войти" in head):
        return "Cookie мёртвый (редирект на login)"
    if "challenge" in head or "captcha" in head:
        return "Challenge / CAPTCHA"
    return None


# ===================== ENGINES =====================
def fetch_cffi(url: str, ua: str, proxies: Optional[dict]) -> Tuple[int, str, str]:
    if not HAS_CFFI:
        raise RuntimeError("curl_cffi не установлен")
    r = cffi_requests.get(
        url,
        headers=base_headers(ua),
        timeout=45,
        allow_redirects=True,
        proxies=proxies,
        impersonate="chrome131",
    )
    return r.status_code, r.text or "", str(getattr(r, "url", url) or url)


def fetch_cloudscraper(url: str, ua: str, proxies: Optional[dict]) -> Tuple[int, str, str]:
    if not HAS_CS:
        raise RuntimeError("cloudscraper не установлен")
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "android", "mobile": True}
    )
    r = scraper.get(
        url,
        headers=base_headers(ua),
        timeout=45,
        allow_redirects=True,
        proxies=proxies,
    )
    return r.status_code, r.text or "", str(getattr(r, "url", url) or url)


def fetch_requests(url: str, ua: str, proxies: Optional[dict]) -> Tuple[int, str, str]:
    r = requests.get(
        url,
        headers=base_headers(ua),
        timeout=45,
        allow_redirects=True,
        proxies=proxies,
    )
    return r.status_code, r.text or "", str(getattr(r, "url", url) or url)


ENGINES = []
if HAS_CFFI:
    ENGINES.append(("curl_cffi", fetch_cffi))
if HAS_CS:
    ENGINES.append(("cloudscraper", fetch_cloudscraper))
ENGINES.append(("requests", fetch_requests))


def smart_fetch(url: str) -> str:
    errors: List[str] = []
    for engine_name, engine in ENGINES:
        for ua in UA_LIST:
            for proxies in proxy_list():
                tag = "direct" if proxies is None else (proxies.get("http") or "?")
                try:
                    print(f"[try] {engine_name} | {tag}")
                    status, text, final = engine(url, ua, proxies)
                    err = check_error(status, text, final)
                    if err:
                        print(f"  fail: {err}")
                        errors.append(f"{engine_name}/{tag}: {err}")
                        time.sleep(0.35)
                        continue
                    print(f"  OK {engine_name} via {tag} len={len(text)}")
                    return text
                except Exception as e:
                    msg = f"{engine_name}/{tag}: {type(e).__name__}: {e}"
                    print(f"  fail: {msg}")
                    errors.append(msg)
                    time.sleep(0.25)
    raise RuntimeError(
        "Все бесплатные варианты провалились\n"
        f"cookie_len={len(FULL_COOKIE)} free_proxies={bool(FREE_PROXIES)}\n"
        f"url={url}\n"
        + "\n".join(errors[-12:])
    )


# ===================== PARSE =====================
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
    lines = [
        f"<b>{title}</b>",
        f"<i>{now_msk()}</i>",
        f"Клуб: <b>{CLUB_NAME}</b>",
        "",
    ]
    if not rows:
        lines.append("⚠️ Топ не разобран (вёрстка / cookie / защита)")
    else:
        for i, (name, score) in enumerate(rows):
            p = medals[i] if i < 3 else f"{i + 1}."
            lines.append(f"{p} <b>{name}</b> — {score}")
    return "\n".join(lines)


def format_history(items: List[str]) -> str:
    lines = [
        "<b>📜 Последние вклады</b>",
        f"<i>{now_msk()}</i>",
        f"Клуб: <b>{CLUB_NAME}</b>",
        "",
    ]
    if not items:
        lines.append("⚠️ История пуста / не распарсилась")
    else:
        for i, t in enumerate(items, 1):
            lines.append(f"{i}. {t}")
    return "\n".join(lines)


def main() -> int:
    print("=" * 55)
    print("MODE        =", MODE)
    print("CLUB_SLUG   =", CLUB_SLUG)
    print("BOOST_URL   =", BOOST_URL)
    print("HISTORY_URL =", HISTORY_URL)
    print("cookie_len  =", len(FULL_COOKIE))
    print("FREE_PROXIES=", bool(FREE_PROXIES))
    print("engines     =", [n for n, _ in ENGINES])
    print("=" * 55)

    if not BOT_TOKEN or not CHAT_ID:
        die("Нет BOT_TOKEN или CHAT_ID")

    if not FULL_COOKIE or len(FULL_COOKIE) < 40:
        die("FULL_COOKIE пустой или короткий")

    try:
        if MODE in ("daily", "weekly", "all"):
            html = smart_fetch(BOOST_URL)
            rows = parse_boost_top(html)
            if MODE == "weekly":
                title = "📊 Топ за неделю (boost)"
            elif MODE == "daily":
                title = "📊 Топ за сутки (boost)"
            else:
                title = "📊 Топ (boost)"
            send_telegram(format_top(title, rows))
            print("top rows:", len(rows))

        if MODE in ("recent", "all"):
            html = smart_fetch(HISTORY_URL)
            items = parse_history(html)
            send_telegram(format_history(items))
            print("history lines:", len(items))

        if MODE not in ("daily", "weekly", "recent", "all"):
            die(f"Unknown MODE={MODE}")

        return 0
    except Exception as e:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        die(str(e))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

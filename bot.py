#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MangaBuff club bot — FREE multi-engine combо
Стратегии: curl_cffi → cloudscraper → requests
Без residential proxy (гарантии обхода DDoS-Guard нет).
"""

from __future__ import annotations

import os
import re
import sys
import time
import traceback
from datetime import datetime
from typing import Callable, List, Optional, Tuple
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

# optional engines
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

# -------- env --------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()
FULL_COOKIE = os.environ.get("FULL_COOKIE", "").strip()
CLUB_SLUG = os.environ.get("CLUB_SLUG", "utinoe-bratstvo").strip()
MODE = os.environ.get("MODE", "all").strip().lower()  # daily|weekly|recent|all
FREE_PROXIES = os.environ.get("FREE_PROXIES", "").strip()  # optional: http://ip:port,http://ip2:port

BASE = "https://mangabuff.ru"
CLUB_NAME = "Утиное Братство"
MSK = ZoneInfo("Europe/Moscow")

UA_LIST = [
    "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]

BAD_WORDS = (
    "замен", "опыт", "сегодня", "доступно", "карт", "владел", "штраф",
    "попыт", "бесплат", "платн", "неделя", "сутки", "месяц", "правил",
    "клуб", "boost", "history", "войти", "регистр",
)


def now_msk() -> str:
    return datetime.now(MSK).strftime("%d.%m.%Y, %H:%M МСК")


def die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    try:
        if BOT_TOKEN and CHAT_ID:
            send_telegram(f"❌ <b>MangaBuff bot</b>\n<code>{msg[:3500]}</code>")
    except Exception:
        pass
    raise SystemExit(code)


def cookie_header() -> str:
    return FULL_COOKIE


def xsrf_from_cookie() -> Optional[str]:
    m = re.search(r"(?:^|;\s*)XSRF-TOKEN=([^;]+)", FULL_COOKIE)
    if not m:
        return None
    return unquote(m.group(1))


def base_headers(ua: str) -> dict:
    h = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "Referer": f"{BASE}/clubs/{CLUB_SLUG}/boost",
        "Origin": BASE,
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
    }
    if FULL_COOKIE:
        h["Cookie"] = FULL_COOKIE
    xsrf = xsrf_from_cookie()
    if xsrf:
        h["X-XSRF-TOKEN"] = xsrf
        h["X-Requested-With"] = "XMLHttpRequest"
    return h


def proxy_list() -> List[Optional[dict]]:
    """None first = direct. Then optional free proxies from env."""
    out: List[Optional[dict]] = [None]
    if not FREE_PROXIES:
        return out
    for p in FREE_PROXIES.split(","):
        p = p.strip()
        if not p:
            continue
        out.append({"http": p, "https": p})
    return out


def is_blocked(status: int, text: str, final_url: str) -> Optional[str]:
    head = (text or "")[:1200].lower()
    if status == 403 or "ddos-guard" in head or "ddos guard" in head:
        return f"403/DDoS-Guard status={status} len={len(text or '')}"
    if status == 429:
        return f"429 Too Many Requests len={len(text or '')}"
    if status != 200:
        return f"HTTP {status} len={len(text or '')}"
    if "/login" in (final_url or "") and ("login" in head or "войти" in head):
        return "Redirect to login — cookie dead/expired"
    if len(text or "") < 800 and ("challenge" in head or "captcha" in head):
        return "Challenge/captcha page"
    return None


# ---------------- engines ----------------

def fetch_cffi(url: str, ua: str, proxies: Optional[dict]) -> Tuple[int, str, str]:
    if not HAS_CFFI:
        raise RuntimeError("curl_cffi not installed")
    sess = cffi_requests.Session()
    r = sess.get(
        url,
        headers=base_headers(ua),
        timeout=45,
        allow_redirects=True,
        proxies=proxies,
        impersonate="chrome131",
    )
    return r.status_code, r.text or "", getattr(r, "url", url) or url


def fetch_cloudscraper(url: str, ua: str, proxies: Optional[dict]) -> Tuple[int, str, str]:
    if not HAS_CS:
        raise RuntimeError("cloudscraper not installed")
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
    return r.status_code, r.text or "", getattr(r, "url", url) or url


def fetch_requests(url: str, ua: str, proxies: Optional[dict]) -> Tuple[int, str, str]:
    s = requests.Session()
    r = s.get(
        url,
        headers=base_headers(ua),
        timeout=45,
        allow_redirects=True,
        proxies=proxies,
    )
    return r.status_code, r.text or "", getattr(r, "url", url) or url


ENGINES: List[Tuple[str, Callable]] = []
if HAS_CFFI:
    ENGINES.append(("curl_cffi", fetch_cffi))
if HAS_CS:
    ENGINES.append(("cloudscraper", fetch_cloudscraper))
ENGINES.append(("requests", fetch_requests))


def smart_fetch(url: str) -> str:
    """Пробует все free-engines × UA × (direct + free proxies)."""
    errors = []
    for engine_name, engine in ENGINES:
        for ua in UA_LIST:
            for proxies in proxy_list():
                proxy_tag = "direct" if proxies is None else str(proxies.get("http"))
                try:
                    print(f"[try] {engine_name} | {proxy_tag} | ua={ua[:40]}...")
                    status, text, final = engine(url, ua, proxies)
                    bad = is_blocked(status, text, final)
                    if bad:
                        msg = f"{engine_name}/{proxy_tag}: {bad}"
                        print("  fail:", msg)
                        errors.append(msg)
                        time.sleep(0.8)
                        continue
                    print(f"  OK {engine_name} status={status} len={len(text)}")
                    return text
                except Exception as e:
                    msg = f"{engine_name}/{proxy_tag}: EXC {type(e).__name__}: {e}"
                    print("  fail:", msg)
                    errors.append(msg)
                    time.sleep(0.5)
    # всё упало
    summary = " | ".join(errors[-12:])  # последние ошибки
    raise RuntimeError(
        "Все free-попытки провалились.\n"
        f"cookie_len={len(FULL_COOKIE)} engines={ [n for n,_ in ENGINES] }\n"
        f"last_errors: {summary}\n"
        "Без residential IP DDoS-Guard часто режет GitHub/Render."
    )


# ---------------- parse ----------------

def parse_boost_top(html: str, limit: int = 15) -> List[Tuple[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    results: List[Tuple[str, str]] = []
    seen = set()

    selectors = (
        "a[href*='/users/'], .user-name, .nickname, "
        "[class*='member'], [class*='boost'], [class*='rating'], "
        "[class*='top'], li, tr, td, div"
    )
    for el in soup.select(selectors):
        text = " ".join(el.get_text(" ", strip=True).split())
        if not text or len(text) > 90:
            continue
        m = re.search(r"^(.+?)\s+(\d{1,7})$", text)
        if not m:
            continue
        name, score = m.group(1).strip(), m.group(2)
        low = name.lower()
        if any(b in low for b in BAD_WORDS):
            continue
        if name in seen:
            continue
        if not re.search(r"[A-Za-zА-Яа-я]", name):
            continue
        if name.isdigit():
            continue
        seen.add(name)
        results.append((name, score))
        if len(results) >= limit:
            break

    if len(results) < 5:
        for line in soup.get_text("\n", strip=True).splitlines():
            line = " ".join(line.split())
            m = re.search(r"^([A-Za-zА-Яа-я0-9_ .\-]{2,40})\s+(\d{1,7})$", line)
            if not m:
                continue
            name, score = m.group(1).strip(), m.group(2)
            low = name.lower()
            if any(b in low for b in BAD_WORDS) or name in seen:
                continue
            if not re.search(r"[A-Za-zА-Яа-я]", name):
                continue
            seen.add(name)
            results.append((name, score))
            if len(results) >= limit:
                break
    return results[:limit]


def parse_history(html: str, limit: int = 10) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    out: List[str] = []
    seen = set()
    for el in soup.select(
        "li, tr, .history-item, [class*='history'], [class*='log'], "
        "[class*='contrib'], [class*='event'], div"
    ):
        t = " ".join(el.get_text(" ", strip=True).split())
        if not (8 < len(t) < 140):
            continue
        if t in seen:
            continue
        if not (re.search(r"\d", t) or re.search(r"[A-Za-zА-Яа-я]{3,}", t)):
            continue
        low = t.lower()
        if any(b in low for b in ("cookie", "javascript", "ddos")):
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= limit:
            break
    return out[:limit]


def format_top(title: str, rows: List[Tuple[str, str]]) -> str:
    medals = ["🥇", "🥈", "🥉"]
    lines = [
        f"<b>{title}</b>",
        f"<i>{now_msk()}</i>",
        f"Клуб: <b>{CLUB_NAME}</b>",
        "Источник: /boost",
        "",
    ]
    if not rows:
        lines.append("⚠️ Топ не разобран (вёрстка/cookie/защита).")
        return "\n".join(lines)
    for i, (name, score) in enumerate(rows):
        p = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{p} <b>{name}</b> — {score}")
    return "\n".join(lines)


def format_history(items: List[str]) -> str:
    lines = [
        "<b>📜 Последние вклады</b>",
        f"<i>{now_msk()}</i>",
        f"Клуб: <b>{CLUB_NAME}</b>",
        "Источник: /history",
        "",
    ]
    if not items:
        lines.append("⚠️ История пуста / не распарсилась.")
    else:
        for i, t in enumerate(items, 1):
            lines.append(f"{i}. {t}")
    return "\n".join(lines)


def send_telegram(text: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError("Нет BOT_TOKEN или CHAT_ID")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(
        url,
        json={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"Telegram {r.status_code}: {r.text[:300]}")


def main() -> int:
    print("=" * 60)
    print("MODE", MODE)
    print("CLUB", CLUB_SLUG)
    print("cookie_len", len(FULL_COOKIE))
    print("engines", [n for n, _ in ENGINES])
    print("HAS_CFFI", HAS_CFFI, "HAS_CS", HAS_CS)
    print("free_proxies", bool(FREE_PROXIES))
    print("=" * 60)

    if not BOT_TOKEN or not CHAT_ID:
        die("Нужны secrets: BOT_TOKEN и CHAT_ID")

    if not FULL_COOKIE or len(FULL_COOKIE) < 40:
        die(
            "FULL_COOKIE пустой или слишком короткий.\n"
            "Settings → Secrets → FULL_COOKIE = вся строка cookies."
        )

    boost_url = f"{BASE}/clubs/{CLUB_SLUG}/boost"
    history_url = f"{BASE}/clubs/{CLUB_SLUG}/history"

    try:
        if MODE in ("daily", "weekly", "all"):
            html = smart_fetch(boost_url)
            rows = parse_boost_top(html)
            title = "📊 Топ за сутки (boost)" if MODE == "daily" else "📊 Топ (boost)"
            if MODE == "weekly":
                title = "📊 Топ за неделю (boost)"
            send_telegram(format_top(title, rows))
            print("top rows", len(rows))

        if MODE in ("recent", "all"):
            html = smart_fetch(history_url)
            hist = parse_history(html)
            send_telegram(format_history(hist))
            print("history lines", len(hist))

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

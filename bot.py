#!/usr/bin/env python3
import os, re, sys
from datetime import datetime
from urllib.parse import unquote
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.environ["BOT_TOKEN"].strip()
CHAT_ID = os.environ["CHAT_ID"].strip()
FULL_COOKIE = os.environ.get("FULL_COOKIE", "").strip()
CLUB_SLUG = os.environ.get("CLUB_SLUG", "utinoe-bratstvo").strip()
MODE = os.environ.get("MODE", "all").strip().lower()

BASE = "https://mangabuff.ru"
CLUB = "Утиное Братство"
MSK = ZoneInfo("Europe/Moscow")
UA = "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 Chrome/131.0.0.0 Mobile Safari/537.36"

def now():
    return datetime.now(MSK).strftime("%d.%m.%Y, %H:%M МСК")

def get(url):
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Referer": f"{BASE}/clubs/{CLUB_SLUG}/boost",
        "Origin": BASE,
    })
    if FULL_COOKIE:
        s.headers["Cookie"] = FULL_COOKIE
        m = re.search(r"XSRF-TOKEN=([^;]+)", FULL_COOKIE)
        if m:
            s.headers["X-XSRF-TOKEN"] = unquote(m.group(1))
    r = s.get(url, timeout=45)
    t = r.text or ""
    if r.status_code == 403 or "ddos" in t[:500].lower():
        raise RuntimeError(f"403 DDoS-Guard {url}")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    if "/login" in r.url:
        raise RuntimeError("Cookie мёртвый — обнови FULL_COOKIE")
    return t

def parse_top(html, limit=15):
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    bad = ("замен", "опыт", "сегодня", "доступно", "карт", "штраф", "бесплат", "платн")
    for el in soup.select("a[href*='/users/'], li, tr, [class*='member'], [class*='boost']"):
        text = " ".join(el.get_text(" ", strip=True).split())
        m = re.search(r"^(.+?)\s+(\d{1,6})$", text)
        if not m:
            continue
        name, score = m.group(1).strip(), m.group(2)
        if any(b in name.lower() for b in bad) or name in seen:
            continue
        if not re.search(r"[A-Za-zА-Яа-я]", name):
            continue
        seen.add(name)
        out.append((name, score))
        if len(out) >= limit:
            break
    if len(out) < 5:
        for line in soup.get_text("\n").splitlines():
            line = " ".join(line.split())
            m = re.search(r"^([A-Za-zА-Яа-я0-9_ .\-]{2,40})\s+(\d{1,6})$", line)
            if not m:
                continue
            name, score = m.group(1).strip(), m.group(2)
            if any(b in name.lower() for b in bad) or name in seen:
                continue
            seen.add(name)
            out.append((name, score))
            if len(out) >= limit:
                break
    return out[:limit]

def parse_hist(html, limit=10):
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for el in soup.select("li, tr, [class*='history']"):
        t = " ".join(el.get_text(" ", strip=True).split())
        if 8 < len(t) < 120 and t not in seen and (re.search(r"\d", t) or re.search(r"[A-Za-zА-Яа-я]{3,}", t)):
            seen.add(t)
            out.append(t)
        if len(out) >= limit:
            break
    return out

def tg(text):
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"TG {r.status_code}: {r.text[:200]}")

def fmt_top(title, rows):
    m = ["🥇", "🥈", "🥉"]
    lines = [f"<b>{title}</b>", f"<i>{now()}</i>", f"Клуб: <b>{CLUB}</b>", ""]
    if not rows:
        lines.append("⚠️ Топ не разобран (cookie/защита/вёрстка)")
    else:
        for i, (n, s) in enumerate(rows):
            lines.append(f"{m[i] if i < 3 else f'{i+1}.'} <b>{n}</b> — {s}")
    return "\n".join(lines)

def main():
    print("MODE", MODE, "cookie", len(FULL_COOKIE))
    try:
        if MODE in ("daily", "weekly", "all"):
            rows = parse_top(get(f"{BASE}/clubs/{CLUB_SLUG}/boost"))
            tg(fmt_top("📊 Топ (boost)", rows))
            print("top", len(rows))
        if MODE in ("recent", "all"):
            h = parse_hist(get(f"{BASE}/clubs/{CLUB_SLUG}/history"))
            lines = [f"<b>📜 Последние вклады</b>", f"<i>{now()}</i>", f"Клуб: <b>{CLUB}</b>", ""]
            lines += [f"{i}. {t}" for i, t in enumerate(h, 1)] or ["⚠️ Пусто"]
            tg("\n".join(lines))
            print("hist", len(h))
        return 0
    except Exception as e:
        print(e, file=sys.stderr)
        try:
            tg(f"❌ Ошибка\n<code>{e}</code>")
        except Exception:
            pass
        return 1

if __name__ == "__main__":
    raise SystemExit(main())

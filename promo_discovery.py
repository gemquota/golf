#!/usr/bin/env python3
"""Independent discovery of welcome/registration promotions on registered sites.

This deliberately does not use the authenticated bonus API, perceived-value
scoring, or the existing positive-amount filter. A zero or unknown value is a
valid discovery result.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit

import config
import db
import network

PROMO_TERMS = (
    "welcome bonus", "welcome offer", "first deposit bonus",
    "first deposit offer", "first time deposit", "first-deposit",
    "sign up bonus", "signup bonus", "sign-up bonus", "sign up offer",
    "registration bonus", "register bonus", "new member bonus",
    "new customer bonus", "new player bonus", "joining bonus",
    "new account bonus", "deposit match", "bonus on your first deposit",
    "first recharge bonus", "new user bonus",
)
PROMO_LINK_HINTS = (
    "promotion", "promotions", "bonus", "welcome", "register",
    "signup", "sign-up", "new-member", "first-deposit", "offers",
)
TERM_RE = re.compile("|".join(re.escape(x) for x in PROMO_TERMS), re.I)
PERCENT_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d{1,2})?)\s*%")
MONEY = r"(?:A\$|AU\$|AUD\s*|\$)\s*([\d,]+(?:\.\d{1,2})?)"
MAX_PAYOUT_PATTERNS = (
    re.compile(r"(?:maximum|max\.?|up\s+to|capped\s+at)\s+(?:payout|cashout|withdrawal|win(?:nings)?|bonus)?\s*[:\-]?\s*" + MONEY, re.I),
    re.compile(MONEY + r"\s*(?:maximum|max\.?\s+)?(?:payout|cashout|withdrawal|win(?:nings)?)", re.I),
)
BONUS_AMOUNT_RE = re.compile(r"(?:bonus|deposit\s+match|match)\D{0,35}" + MONEY, re.I)
ROLLOVER_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:x|times)\s*(?:wager(?:ing)?|turnover|rollover)?|"
    r"(?:wager(?:ing)?|turnover|rollover)\D{0,20}(\d+(?:\.\d+)?)\s*(?:x|times)",
    re.I,
)
MAX_PAGES_DEFAULT = 12
DELAY_DEFAULT = 1.5


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._capture_title = False
        self.title_parts: list[str] = []
        self._anchor_text: list[str] | None = None
        self._anchor_href = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == "title":
            self._capture_title = True
        if tag.lower() == "a" and attrs.get("href"):
            self._anchor_href = attrs["href"]
            self._anchor_text = []

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self._capture_title = False
        if tag.lower() == "a" and self._anchor_text is not None:
            label = " ".join(self._anchor_text).strip()
            self.links.append((self._anchor_href, label))
            self._anchor_text = None
            self._anchor_href = ""

    def handle_data(self, data):
        value = " ".join(data.split())
        if not value:
            return
        self.parts.append(value)
        if self._capture_title:
            self.title_parts.append(value)
        if self._anchor_text is not None:
            self._anchor_text.append(value)

    @property
    def text(self):
        return " ".join(self.parts)

    @property
    def title(self):
        return " ".join(self.title_parts).strip()


@dataclass
class Promotion:
    merchant_id: str
    merchant_name: str
    source_url: str
    page_url: str
    title: str
    matched_terms: str
    bonus_percentage: str
    max_payout: str
    bonus_amount: str
    rollover_requirement: str
    registered_account: str
    snippet: str
    http_status: int
    discovered_at: str
    content_hash: str


def _money_value(match):
    return f"AUD {float(match.group(1).replace(',', '')):g}"


def extract_fields(text: str) -> dict[str, str]:
    """Extract independently; missing/zero values never invalidate a match."""
    clean = re.sub(r"\s+", " ", text)
    terms = sorted({m.group(0).lower() for m in TERM_RE.finditer(clean)})
    max_payout = ""
    for pattern in MAX_PAYOUT_PATTERNS:
        match = pattern.search(clean)
        if match:
            max_payout = _money_value(match)
            break
    amount_match = BONUS_AMOUNT_RE.search(clean)
    rollover_match = ROLLOVER_RE.search(clean)
    percentages = PERCENT_RE.findall(clean)
    return {
        "matched_terms": " | ".join(terms),
        "bonus_percentage": " | ".join(dict.fromkeys(f"{p}%" for p in percentages)),
        "max_payout": max_payout,
        "bonus_amount": _money_value(amount_match) if amount_match else "",
        "rollover_requirement": (
            f"{rollover_match.group(1) or rollover_match.group(2)}x"
            if rollover_match else ""
        ),
    }


def _same_origin(base: str, candidate: str) -> bool:
    a, b = urlsplit(base), urlsplit(candidate)
    return (a.scheme in ("http", "https") and b.scheme in ("http", "https")
            and a.netloc.casefold() == b.netloc.casefold())


def _candidate_links(base_url: str, links: list[tuple[str, str]]) -> list[str]:
    found = []
    seen = set()
    for href, label in links:
        target, _fragment = urldefrag(urljoin(base_url, href))
        hint = (label + " " + urlsplit(target).path).casefold()
        if not any(term in hint for term in PROMO_LINK_HINTS):
            continue
        if not _same_origin(base_url, target) or target in seen:
            continue
        if urlsplit(target).path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".pdf", ".zip")):
            continue
        seen.add(target)
        found.append(target)
    return found


def _account_for(url: str, state: dict) -> str:
    item = state.get(url, {})
    if isinstance(item, dict) and item.get("status") == "registered":
        return str(item.get("account_id") or "")
    return ""


def _site_records():
    db.initialize_database()
    rows = db.execute(
        "SELECT url, merchant_id, merchant_name FROM sites WHERE COALESCE(active, 1) != 0 ORDER BY url"
    )
    # Include configured URLs that have not yet entered the authenticated scraper DB.
    configured = Path("in/config/urls.txt")
    known = {row[0] for row in rows}
    for url in configured.read_text(encoding="utf-8").splitlines() if configured.exists() else []:
        url = url.strip()
        if url and url not in known:
            rows.append((url, "", ""))
    return rows


def _ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS promotional_discoveries (
            content_hash TEXT PRIMARY KEY,
            merchant_id TEXT,
            merchant_name TEXT,
            source_url TEXT NOT NULL,
            page_url TEXT NOT NULL,
            title TEXT,
            matched_terms TEXT,
            bonus_percentage TEXT,
            max_payout TEXT,
            bonus_amount TEXT,
            rollover_requirement TEXT,
            registered_account TEXT,
            snippet TEXT,
            http_status INTEGER,
            discovered_at TEXT,
            last_seen_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_promo_merchant ON promotional_discoveries(merchant_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_promo_source ON promotional_discoveries(source_url)")
    conn.commit()


def scan_site(session, source_url, merchant_id="", merchant_name="", account_id="",
              max_pages=MAX_PAGES_DEFAULT, delay=DELAY_DEFAULT):
    queue = [source_url]
    visited = set()
    results = []
    while queue and len(visited) < max_pages:
        page_url = queue.pop(0)
        if page_url in visited:
            continue
        visited.add(page_url)
        try:
            response = network.get_page_response(session, page_url)
        except Exception as exc:
            print(f"[page-error] {page_url}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue

        if not merchant_id or not merchant_name:
            try:
                parsed_id, parsed_name = network.parse_merchant_info(response.text)
                merchant_id = merchant_id or str(parsed_id)
                merchant_name = merchant_name or str(parsed_name)
            except (ValueError, TypeError):
                pass

        parser = PageParser()
        try:
            parser.feed(response.text)
        except Exception:
            continue
        fields = extract_fields(parser.text)
        if fields["matched_terms"]:
            snippet = parser.text[:1200]
            digest = hashlib.sha256(
                (source_url + "|" + response.url + "|" + parser.title + "|" + fields["matched_terms"]).encode()
            ).hexdigest()
            results.append(Promotion(
                merchant_id=str(merchant_id or ""),
                merchant_name=str(merchant_name or ""),
                source_url=source_url,
                page_url=response.url,
                title=parser.title[:300],
                matched_terms=fields["matched_terms"],
                bonus_percentage=fields["bonus_percentage"],
                max_payout=fields["max_payout"],
                bonus_amount=fields["bonus_amount"],
                rollover_requirement=fields["rollover_requirement"],
                registered_account=account_id,
                snippet=snippet,
                http_status=response.status_code,
                discovered_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                content_hash=digest,
            ))
        for target in _candidate_links(response.url, parser.links):
            if target not in visited and target not in queue:
                queue.append(target)
        if delay:
            time.sleep(delay)
    return results


def run(output: Path, max_pages=MAX_PAGES_DEFAULT, delay=DELAY_DEFAULT, limit=0):
    state_path = Path("data/account_state.json")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        if not isinstance(state, dict):
            state = {}
    except (OSError, ValueError):
        state = {}

    records = _site_records()
    if limit:
        records = records[:limit]
    db_path = Path(db.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    _ensure_table(conn)
    csv_path = output
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(Promotion.__dataclass_fields__)
    total_pages = total_matches = 0
    try:
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for index, (url, merchant_id, merchant_name) in enumerate(records, 1):
                account_id = _account_for(url, state)
                session = network.create_session()
                try:
                    promos = scan_site(
                        session, url, merchant_id or "", merchant_name or "",
                        account_id, max_pages=max_pages, delay=delay,
                    )
                finally:
                    session.close()
                total_pages += min(max_pages, 1 + len(promos))
                for promo in promos:
                    row = asdict(promo)
                    writer.writerow(row)
                    conn.execute("""
                        INSERT INTO promotional_discoveries (
                            content_hash, merchant_id, merchant_name, source_url,
                            page_url, title, matched_terms, bonus_percentage,
                            max_payout, bonus_amount, rollover_requirement,
                            registered_account, snippet, http_status, discovered_at,
                            last_seen_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(content_hash) DO UPDATE SET
                            merchant_id=excluded.merchant_id,
                            merchant_name=excluded.merchant_name,
                            bonus_percentage=excluded.bonus_percentage,
                            max_payout=excluded.max_payout,
                            bonus_amount=excluded.bonus_amount,
                            rollover_requirement=excluded.rollover_requirement,
                            registered_account=excluded.registered_account,
                            snippet=excluded.snippet,
                            http_status=excluded.http_status,
                            last_seen_at=excluded.discovered_at
                    """, (
                        promo.content_hash, promo.merchant_id, promo.merchant_name,
                        promo.source_url, promo.page_url, promo.title,
                        promo.matched_terms, promo.bonus_percentage, promo.max_payout,
                        promo.bonus_amount, promo.rollover_requirement,
                        promo.registered_account, promo.snippet, promo.http_status,
                        promo.discovered_at, promo.discovered_at,
                    ))
                    total_matches += 1
                conn.commit()
                print(f"[{index}/{len(records)}] {url}: {len(promos)} promotional page(s)")
    finally:
        conn.close()
    print(f"Completed: {len(records)} sites, {total_matches} matches. CSV: {csv_path}")
    return total_matches


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/promotional_discoveries.csv"))
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES_DEFAULT)
    parser.add_argument("--delay", type=float, default=DELAY_DEFAULT)
    parser.add_argument("--limit", type=int, default=0, help="scan only the first N sites (0 = all)")
    args = parser.parse_args()
    if args.max_pages < 1 or args.delay < 0 or args.limit < 0:
        parser.error("--max-pages must be positive; --delay and --limit cannot be negative")
    run(args.output, args.max_pages, args.delay, args.limit)


if __name__ == "__main__":
    main()

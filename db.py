import csv, datetime, difflib, hashlib, json, re, sqlite3, threading
from contextlib import contextmanager
from math import log2, log10, pow
from pathlib import Path

import config

TZ = datetime.timezone(datetime.timedelta(hours=10))
DB_PATH = "data/base.db"
_csv_cache: dict = {}
_cache: dict[str, sqlite3.Connection] = {}

# A single SQLite connection is shared by scraper workers. Serialize every
# cursor/transaction operation; check_same_thread=False alone is not thread-safe.
_db_lock = threading.RLock()

HEADERS = ["url","mname","id","name","transactiontype","bonusfixed","amount","minwithdraw",
    "maxwithdraw","rollover","balance","claimconfig","claimcondition","bonus","bonusrandom",
    "reset","mintopup","maxtopup","referlink","perceived_value","is_new"]

# Canonical schema names (post-ungolf).
TABLE_SITES = "sites"
TABLE_BONUSES = "bonuses"
TABLE_SESSIONS = "sessions"
TABLE_SCRAPE_RUNS = "scrape_runs"
TABLE_LOGS = "logs"
TABLE_BONUSES_FTS = "bonuses_fts"

def get_connection():
    # RLock is re-entrant because cursor_context also holds it while calling here.
    with _db_lock:
        if DB_PATH not in _cache:
            conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
            # WAL helps external readers; busy_timeout handles other connections.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=30000")
            _cache[DB_PATH] = conn
        return _cache[DB_PATH]

@contextmanager
def cursor_context():
    # Hold the lock across execute/fetch AND commit/rollback. Locking only
    # connection creation would still let worker threads corrupt each other's
    # transaction/cursor state.
    with _db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

def execute(query, params=()):
    with cursor_context() as c:
        c.execute(query, params)
        return c.fetchall()

JSONL_PATH = Path("data/events.jsonl")

# Ordered, named migrations applied once each; recorded in schema_version.
# 001 kept for historical DBs that already recorded it before the ungolf rename.
MIGRATIONS = (
    ("001_add_ec_column", None),  # handled specially / no-op on new schema
    ("002_ungolf_schema", None),  # applied by migrate_ungolf_schema()
)

_CANONICAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS sites(
    url TEXT PRIMARY KEY,
    merchant_name,
    referral_url,
    short_url,
    active INT DEFAULT 1,
    updated_at DATETIME,
    error_code INTEGER
);
CREATE TABLE IF NOT EXISTS bonuses(
    bonus_uid TEXT PRIMARY KEY,
    external_id,
    url,
    amount REAL,
    perceived_value REAL,
    wager REAL,
    claim REAL,
    kind,
    raw_json,
    content_hash,
    expiry DATETIME,
    fingerprint TEXT,
    mirrors TEXT,
    first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_seen DATETIME,
    merchant_name,
    name
);
CREATE TABLE IF NOT EXISTS sessions(
    user_id,
    url,
    cookies BLOB,
    session_data BLOB,
    user_agent,
    ip,
    ok INT DEFAULT 1,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(user_id, url)
);
CREATE TABLE IF NOT EXISTS scrape_runs(
    run_id,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    duration REAL,
    count INT,
    new_count INT,
    sum_perceived_value REAL,
    error_count INT
);
CREATE TABLE IF NOT EXISTS logs(
    id INTEGER PRIMARY KEY,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    level,
    source,
    message
);
"""

_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS bonuses_fts USING fts5(
    bonus_uid UNINDEXED, external_id, url, raw_json,
    content='bonuses', content_rowid='rowid'
);
CREATE TRIGGER IF NOT EXISTS bonuses_ai AFTER INSERT ON bonuses BEGIN
    INSERT INTO bonuses_fts(rowid, bonus_uid, external_id, url, raw_json)
    VALUES (new.rowid, new.bonus_uid, new.external_id, new.url, new.raw_json);
END;
CREATE TRIGGER IF NOT EXISTS bonuses_ad AFTER DELETE ON bonuses BEGIN
    INSERT INTO bonuses_fts(bonuses_fts, rowid, bonus_uid, external_id, url, raw_json)
    VALUES ('delete', old.rowid, old.bonus_uid, old.external_id, old.url, old.raw_json);
END;
CREATE TRIGGER IF NOT EXISTS bonuses_au AFTER UPDATE ON bonuses BEGIN
    INSERT INTO bonuses_fts(bonuses_fts, rowid, bonus_uid, external_id, url, raw_json)
    VALUES ('delete', old.rowid, old.bonus_uid, old.external_id, old.url, old.raw_json);
    INSERT INTO bonuses_fts(rowid, bonus_uid, external_id, url, raw_json)
    VALUES (new.rowid, new.bonus_uid, new.external_id, new.url, new.raw_json);
END;
"""

# Table rename map: legacy golfed name -> canonical name.
_TABLE_RENAMES = (
    ("t", "sites"),
    ("b", "bonuses"),
    ("s", "sessions"),
    ("m", "scrape_runs"),
    ("l", "logs"),
)

# Column renames per canonical table: (old, new)
_COLUMN_RENAMES = {
    "sites": (
        ("u", "url"),
        ("m", "merchant_name"),
        ("p", "referral_url"),
        ("g", "short_url"),
        ("a", "active"),
        ("ts", "updated_at"),
        ("ec", "error_code"),
    ),
    "bonuses": (
        ("uid", "bonus_uid"),
        ("eid", "external_id"),
        ("u", "url"),
        ("v", "amount"),
        ("pv", "perceived_value"),
        ("w", "wager"),
        ("c", "claim"),
        ("t", "kind"),
        ("raw", "raw_json"),
        ("h", "content_hash"),
        ("exp", "expiry"),
        ("fp", "fingerprint"),
        ("s1", "first_seen"),
        ("sl", "last_seen"),
        ("mname", "merchant_name"),
    ),
    "sessions": (
        ("uid", "user_id"),
        ("u", "url"),
        ("ck", "cookies"),
        ("data", "session_data"),
        ("ua", "user_agent"),
        ("ts", "updated_at"),
    ),
    "scrape_runs": (
        ("rid", "run_id"),
        ("ts", "created_at"),
        ("dur", "duration"),
        ("cnt", "count"),
        ("new", "new_count"),
        ("spv", "sum_perceived_value"),
        ("err", "error_count"),
    ),
    "logs": (
        ("ts", "created_at"),
        ("lvl", "level"),
        ("src", "source"),
        ("msg", "message"),
    ),
}


def _table_names(cursor):
    return {row[0] for row in cursor.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
    ).fetchall()}


def _columns(cursor, table):
    return {row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()}


def _drop_legacy_fts(cursor):
    for trigger in ("b_ai", "b_ad", "b_au", "bonuses_ai", "bonuses_ad", "bonuses_au"):
        cursor.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    for fts in ("b_fts", "bonuses_fts"):
        cursor.execute(f"DROP TABLE IF EXISTS {fts}")


def migrate_ungolf_schema(cursor=None):
    """Idempotent rename of golfed tables/columns to clear names.

    Safe to call repeatedly. Works with a provided cursor (inside an existing
    transaction) or opens its own cursor_context.
    """
    def _run(c):
        names = _table_names(c)
        needs_table_rename = any(old in names for old, _ in _TABLE_RENAMES)
        needs_column_work = False
        for table, renames in _COLUMN_RENAMES.items():
            candidate = table
            if candidate not in names:
                # Look at the pre-rename legacy table name.
                legacy = next((old for old, new in _TABLE_RENAMES if new == table), None)
                candidate = legacy if legacy in names else None
            if not candidate:
                continue
            cols = _columns(c, candidate)
            if any(old in cols and new not in cols for old, new in renames):
                needs_column_work = True
                break

        if needs_table_rename or needs_column_work:
            _drop_legacy_fts(c)

        for old, new in _TABLE_RENAMES:
            names = _table_names(c)
            if old in names and new not in names:
                c.execute(f"ALTER TABLE {old} RENAME TO {new}")

        for table, renames in _COLUMN_RENAMES.items():
            names = _table_names(c)
            if table not in names:
                continue
            cols = _columns(c, table)
            for old, new in renames:
                if old in cols and new not in cols:
                    c.execute(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")
                    cols.discard(old)
                    cols.add(new)

        names = _table_names(c)
        if "bonuses" in names and "bonuses_fts" not in names:
            c.executescript(_FTS_SCHEMA)
            c.execute(
                "INSERT INTO bonuses_fts(rowid, bonus_uid, external_id, url, raw_json) "
                "SELECT rowid, bonus_uid, external_id, url, raw_json FROM bonuses"
            )

    if cursor is not None:
        _run(cursor)
        return
    with cursor_context() as c:
        _run(c)


def initialize_database():
    with cursor_context() as c:
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute(
            "CREATE TABLE IF NOT EXISTS schema_version("
            "version TEXT PRIMARY KEY, applied DATETIME DEFAULT CURRENT_TIMESTAMP)"
        )
        applied = {row[0] for row in c.execute("SELECT version FROM schema_version").fetchall()}
        names = _table_names(c)
        legacy = any(old in names for old, _new in _TABLE_RENAMES)

        # Historical: add ec on legacy t before rename.
        if "001_add_ec_column" not in applied:
            try:
                if "t" in names and "ec" not in _columns(c, "t"):
                    c.execute("ALTER TABLE t ADD COLUMN ec INTEGER")
                elif "sites" in names:
                    cols = _columns(c, "sites")
                    if "error_code" not in cols and "ec" not in cols:
                        c.execute("ALTER TABLE sites ADD COLUMN error_code INTEGER")
            except sqlite3.OperationalError:
                pass
            c.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (?)", ("001_add_ec_column",))
            applied.add("001_add_ec_column")

        # Rename legacy golfed schema before CREATE IF NOT EXISTS for canonical names,
        # otherwise empty sites/bonuses tables would block ALTER TABLE ... RENAME TO.
        if legacy or "002_ungolf_schema" not in applied:
            migrate_ungolf_schema(c)
            c.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (?)", ("002_ungolf_schema",))
        else:
            migrate_ungolf_schema(c)

        c.executescript(_CANONICAL_SCHEMA)
        # Run IDs are stable per scrape start marker. Keep the latest legacy
        # duplicate before enforcing idempotent writes from maintain_pipeline.
        run_columns = _columns(c, "scrape_runs")
        if "run_id" not in run_columns:
            c.execute("ALTER TABLE scrape_runs ADD COLUMN run_id TEXT")
            run_columns.add("run_id")
        for name, declaration in (
            ("active_sites", "INTEGER"), ("moved_down", "INTEGER"),
            ("attempts", "INTEGER"), ("successes", "INTEGER"),
        ):
            if name not in run_columns:
                c.execute(f"ALTER TABLE scrape_runs ADD COLUMN {name} {declaration}")
        c.execute(
            "DELETE FROM scrape_runs WHERE run_id IS NOT NULL AND rowid NOT IN "
            "(SELECT MAX(rowid) FROM scrape_runs WHERE run_id IS NOT NULL GROUP BY run_id)"
        )
        c.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_scrape_runs_run_id ON scrape_runs(run_id)"
        )
        names = _table_names(c)
        if "bonuses" in names and "bonuses_fts" not in names:
            c.executescript(_FTS_SCHEMA)


def load_session(url, user_id):
    r = execute(
        "SELECT cookies, session_data, updated_at FROM sessions WHERE user_id=? AND url=?",
        (user_id, url),
    )
    if not r:
        return None
    try:
        cookies = json.loads(r[0][0])
        data = json.loads(r[0][1])
    except Exception:
        # Invalid or old pickled data
        return None
    return {"ck": cookies, "data": data, "ts": r[0][2]}

def save_session(url, user_id, cookies, data):
    execute(
        "REPLACE INTO sessions(user_id, url, cookies, session_data, updated_at) "
        "VALUES (?,?,?,?,CURRENT_TIMESTAMP)",
        (user_id, url, json.dumps(cookies), json.dumps(data)),
    )

def _init_csv(path):
    p = Path(path)
    if p.exists():
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="") as f:
        csv.DictWriter(f, HEADERS).writeheader()

def append_csv_row(row, path="data/bonuses.csv"):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", newline="") as f:
        csv.DictWriter(f, fieldnames=list(row.keys())).writerow(row)

def log_event(level, source, message):
    execute("INSERT INTO logs(level, source, message) VALUES (?,?,?)", (level, source, message))
    try:
        JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with JSONL_PATH.open("a") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "lvl": level,
                "src": source,
                "msg": str(message)[:500],
            }) + "\n")
    except Exception:
        pass  # JSONL is best-effort; the DB row above is the source of truth

def search(query, min_pv=0):
    return execute(
        "SELECT bonuses.url, bonuses.external_id, bonuses.amount, bonuses.perceived_value, "
        "bonuses.raw_json FROM bonuses JOIN bonuses_fts ON bonuses.rowid=bonuses_fts.rowid "
        "WHERE bonuses_fts MATCH ? AND bonuses.perceived_value>=? ORDER BY bonuses.perceived_value DESC",
        (query, min_pv),
    )

# --- Bonus filter utilities ---

def _clean(name):
    if not name:
        return ""
    return " ".join(re.sub(r"<[^>]+>", "", name).strip().lower().split())

def is_fuzzy_match(a, b, threshold=0.85):
    if not a or not b:
        return not a and not b
    ca, cb = _clean(a), _clean(b)
    if not ca or not cb:
        return not ca and not cb
    ratio_matches = difflib.SequenceMatcher(None, ca, cb).ratio() >= threshold
    digits_match = re.findall(r"\d+", ca) == re.findall(r"\d+", cb)
    romans_match = re.findall(r"\b(i{1,3}|iv|v|vi{1,3}|ix|x)\b", ca) == re.findall(r"\b(i{1,3}|iv|v|vi{1,3}|ix|x)\b", cb)
    return ratio_matches and digits_match and romans_match

def find_matching_name(name, existing_names, threshold=0.85):
    for c in existing_names:
        if is_fuzzy_match(name, c, threshold):
            return c
    return None

def float_value(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def fingerprint_bonus(bonus):
    raw = f"{bonus.get('name')}|{bonus.get('amount')}|{bonus.get('rollover')}|{bonus.get('minwithdraw')}|{bonus.get('maxwithdraw')}"
    return hashlib.sha256(raw.encode()).hexdigest()

def get_url_scores():
    r = execute("SELECT url, SUM(perceived_value) FROM bonuses GROUP BY url")
    if r:
        return {row[0]: row[1] for row in r}
    return {}

def parse_expiry(text):
    if not text:
        return None
    patterns = [
        (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
        (r"\d{2}/\d{2}/\d{4}", "%d/%m/%Y"),
        (r"\d{2}-\d{2}-\d{4}", "%d-%m-%Y"),
        (r"\d{2}/\d{2}", "%d/%m")
    ]
    for pat, fmt in patterns:
        m = re.search(pat, str(text))
        if not m:
            continue
        try:
            s = m.group(0)
            if fmt == "%d/%m" and len(s) <= 5:
                s = f"{s}/2026"
            dt_format = "%d/%m/%Y" if "/" in s else fmt
            return datetime.datetime.strptime(s, dt_format).replace(tzinfo=TZ)
        except ValueError:
            continue
    return None

def perceived_value(bonus):
    amount = float_value(bonus.get("amount"))
    if amount <= 0:
        return 0.0
    max_w = float_value(bonus.get("maxwithdraw")) or config.DEFAULT_MAX_WITHDRAW
    min_w = float_value(bonus.get("minwithdraw"))
    roll = float_value(bonus.get("rollover"))

    num = 10.0 * log2(max_w + 1) * (1.0 + 0.2 * log10(amount + 1))
    div = max(1.0, max(min_w, amount * roll)) / amount
    return max(0.0, num / pow(max(1.0, div), 1.25) / (1.0 + roll / 20.0))

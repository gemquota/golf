import base64, json, os, re, tempfile, time
from pathlib import Path
import cloudscraper, requests
import config

CACHE_PATH = Path("data/ip_health.json")

def create_session(proxy=None):
    try:
        scraper_session = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
    except Exception:
        # cloudscraper can break on very new Python versions (e.g. Termux 3.14).
        # Degrade to a plain session - some sites don't challenge anyway.
        scraper_session = requests.Session()
    scraper_session.headers.update({
        "User-Agent": config.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    })
    if proxy:
        scraper_session.proxies = {"http": proxy, "https": proxy}
    return scraper_session

def post_json(session, url, data):
    response = session.post(url, data=data, timeout=config.TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("API response must be a JSON object")
    return payload

def _parklogic_redirect(session, html):
    if "<title>Redirecting" not in html or "parklogic" not in html:
        return None
        
    match = re.search(r'"(ey[A-Za-z0-9+/=]{50,})"', html)
    if not match:
        return None
        
    try:
        payload = json.loads(base64.b64decode(match.group(1), validate=True))
        parameters = payload.get("parameters") if isinstance(payload, dict) else None
        if not isinstance(parameters, dict):
            return None
        parameters.update({
            "adBlockingDetected": 0,
            "timezoneBrowser": "Australia/Brisbane",
            "webdriver": 0,
            "gpu": None,
        })
    except (ValueError, TypeError):
        return None

    response = session.post(
        "https://router.parklogic.com/",
        data=json.dumps(payload),
        timeout=config.TIMEOUT,
    )
    response.raise_for_status()
    destination = response.text.strip()
    return destination if destination.startswith(("http://", "https://")) else None

def get_page(session, url):
    response = session.get(url, timeout=config.TIMEOUT)
    response.raise_for_status()
    
    redirect_url = _parklogic_redirect(session, response.text)
    if redirect_url:
        response = session.get(redirect_url, timeout=config.TIMEOUT)
        response.raise_for_status()

    return response.text

def _extract_var(html, name):
    marker = f"var {name} = "
    try:
        start_index = html.index(marker) + len(marker)
        end_index = html.index(";", start_index)
    except ValueError:
        raise ValueError(f"Merchant page is missing a valid {name} declaration") from None
    return html[start_index:end_index].strip().strip(chr(34) + chr(39) + " ")

def parse_merchant_info(html):
    return _extract_var(html, "MERCHANTID"), _extract_var(html, "MERCHANTNAME")

def build_api_url(url):
    return f"{url.rstrip('/')}/api/v1/index.php"

class AuthenticationError(Exception):
    """The site explicitly failed to return an authenticated user session."""


def login(session, url, username, password, merchant_id):
    payload = {
        "module": "/users/login",
        "mobile": username,
        "password": password,
        "merchantId": merchant_id,
        "domainId": "0",
        "accessId": "",
        "accessToken": "",
        "walletIsAdmin": ""
    }
    try:
        response_data = post_json(session, url, payload)
    except requests.exceptions.HTTPError as exc:
        # HTTP 401 is an explicit authentication rejection; 403 may instead
        # mean site-level blocking, so leave it classified as an HTTP failure.
        if exc.response is not None and exc.response.status_code == 401:
            raise AuthenticationError("login failed: HTTP 401 authentication rejected") from exc
        raise
    user_data = response_data.get("data", {}) if isinstance(response_data, dict) else {}
    # The scraper depends on both values for syncData. A 200 response with an
    # API-level login rejection must not be counted as a successful scrape.
    if not isinstance(user_data, dict) or not user_data.get("token") or not user_data.get("id"):
        raise AuthenticationError("login failed: response did not contain token and user id")
    return user_data

def sync_user_data(session, url, merchant_id, access_token, access_id):
    payload = {
        "module": "/users/syncData",
        "merchantId": merchant_id,
        "accessToken": access_token,
        "accessId": access_id,
        "domainId": "0",
        "walletIsAdmin": ""
    }
    return post_json(session, url, payload)

def _load_ip_cache():
    """Return a valid, unexpired reputation cache entry or None."""
    try:
        value = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return None
        timestamp = float(value["ts"])
        score = int(value["score"])
        ip = str(value["ip"]).strip()
        age = time.time() - timestamp
        if 0 <= age < 3600 and ip:
            return score, ip
    except (OSError, ValueError, TypeError, KeyError):
        return None
    return None


def _save_ip_cache(score, ip):
    """Atomically replace the cache so an interrupted write cannot poison later runs."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".ip-health-", dir=str(CACHE_PATH.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"ts": time.time(), "score": int(score), "ip": str(ip)}, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, CACHE_PATH)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def check_ip_reputation(api_key):
    cached = _load_ip_cache()
    if cached is not None:
        return cached

    if not api_key or api_key == "YOUR_KEY_HERE":
        return 0, "Unknown"

    try:
        response = requests.get(
            "https://api.abuseipdb.com/api/v2/check",
            headers={"Accept": "application/json", "Key": api_key},
            params={"maxAgeInDays": "90"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise ValueError("AbuseIPDB response is missing its data object")
        score = int(data["abuseConfidenceScore"])
        ip = str(data["ipAddress"]).strip()
        if not ip or not 0 <= score <= 100:
            raise ValueError("AbuseIPDB returned invalid reputation data")
        _save_ip_cache(score, ip)
        return score, ip
    except Exception:
        return -1, "Error"

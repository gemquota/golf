import base64, json, re, time
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
    return response.json()

def _parklogic_redirect(session, html):
    if "<title>Redirecting" not in html or "parklogic" not in html:
        return None
        
    match = re.search(r'"(ey[A-Za-z0-9+/=]{50,})"', html)
    if not match:
        return None
        
    payload = json.loads(base64.b64decode(match.group(1)))
    payload["parameters"].update({"adBlockingDetected": 0, "timezoneBrowser": "Australia/Sydney", "webdriver": 0, "gpu": None})
    
    response = session.post("https://router.parklogic.com/", data=json.dumps(payload), timeout=config.TIMEOUT)
    if response.text[:4] == "http":
        return response.text
    return None

def get_page(session, url):
    response = session.get(url, timeout=config.TIMEOUT)
    response.raise_for_status()
    
    redirect_url = _parklogic_redirect(session, response.text)
    if redirect_url:
        response = session.get(redirect_url, timeout=config.TIMEOUT)
        
    return response.text

def _extract_var(html, name):
    start_index = html.index(f"var {name} = ") + len(f"var {name} = ")
    return html[start_index:html.index(";", start_index)].strip('" ')

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

def check_ip_reputation(api_key):
    if CACHE_PATH.exists():
        cache_data = json.loads(CACHE_PATH.read_text())
        if time.time() - cache_data["ts"] < 3600:
            return cache_data["score"], cache_data["ip"]
            
    if not api_key or api_key == "YOUR_KEY_HERE":
        return 0, "Unknown"
        
    try:
        response = requests.get(
            "https://api.abuseipdb.com/api/v2/check",
            headers={"Accept": "application/json", "Key": api_key},
            params={"maxAgeInDays": "90"},
            timeout=10
        )
        api_data = response.json()["data"]
        
        CACHE_PATH.write_text(json.dumps({
            "ts": time.time(),
            "score": api_data["abuseConfidenceScore"],
            "ip": api_data["ipAddress"]
        }))
        
        return api_data["abuseConfidenceScore"], api_data["ipAddress"]
    except Exception:
        return -1, "Error"

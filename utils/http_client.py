"""
utils/http_client.py  —  Retry-aware HTTP session
"""
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Any, Optional


def build_session(max_retries: int = 3, backoff: float = 0.8) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=max_retries,
        backoff_factor=backoff,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session


def safe_get(
    session: requests.Session,
    url: str,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: int = 15,
    delay: float = 0.0,
) -> Optional[Any]:
    if delay:
        time.sleep(delay)
    try:
        resp = session.get(url, params=params, headers=headers, timeout=timeout)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 60))
            print(f"  [rate limit] waiting {wait}s...")
            time.sleep(wait)
            resp = session.get(url, params=params, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
        print(f"  [http {resp.status_code}] {url}")
        return None
    except Exception as e:
        print(f"  [error] {url}: {e}")
        return None

import re
import time
import urllib.parse as urlparse
from typing import List, Dict, Optional, Tuple


try:
    import requests
except ImportError:
    requests = None


# Regex patterns for common FB IDs

PATTERNS = [
    # 1) /watch/?v=123456789012345
    ("watch", re.compile(r"[?&]v=(\d{6,})")),
    # 2) /videos/123456789012345  OR /<page>/videos/123456789012345/
    ("video", re.compile(r"/videos/(\d{6,})(?:/|$)")),
    # 3) /reel/123456789012345
    ("reel", re.compile(r"/reel/(\d{6,})(?:/|$)")),
    # 4) /photo/?fbid=123456789012345
    ("photo", re.compile(r"[?&]fbid=(\d{6,})")),
    # 5) /permalink.php?story_fbid=... (returns the story_fbid as the "post id")
    ("permalink_story_fbid", re.compile(r"[?&]story_fbid=([^&]+)")),
    # 6) New-style post links with pfbid (we’ll just return the pfbid)
    ("post_pfbid", re.compile(r"/posts/(pfbid[a-zA-Z0-9]+)")),
    # 7) Sometimes the canonical final URL includes: .../videos/<id>/?v=<id> (fallback repeats ok)
]

def extract_id_from_url(final_url: str) -> Optional[Tuple[str, str]]:
    """
    Try known patterns in order and return (kind, id_str).
    If no match, returns None.
    """
    # First check query patterns separatedly (watch?v=..., photo?fbid=..., permalink story_fbid)
    parsed = urlparse.urlsplit(final_url)
    query = parsed.query

    # Try /watch?v=... and photo?fbid=... and permalink story_fbid first
    for kind, rx in [p for p in PATTERNS if p[0] in ("watch", "photo", "permalink_story_fbid")]:
        if rx.search("?" + query):
            m = rx.search("?" + query)
            if m:
                return (kind, m.group(1))

    # Then try path-based patterns (videos, reel, posts/pfbid)
    path = parsed.path
    for kind, rx in [p for p in PATTERNS if p[0] not in ("watch", "photo", "permalink_story_fbid")]:
        m = rx.search(path)
        if m:
            return (kind, m.group(1))

    # Nothing matched
    return None

def resolve_url_with_requests(u: str, timeout: int = 10) -> Optional[str]:
    """
    Follow redirects cheaply to get the canonical URL.
    Tries HEAD first; if blocked, falls back to GET (streamed).
    """
    if requests is None:
        return None
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    try:
        r = requests.head(u, allow_redirects=True, headers=headers, timeout=timeout)
        if r.url:
            return r.url
    except Exception:
        pass
    try:
        r = requests.get(u, allow_redirects=True, headers=headers, timeout=timeout, stream=True)
        if r.url:
            return r.url
    except Exception:
        pass
    return None

def resolve_url_with_selenium(u: str, driver) -> Optional[str]:

    try:
        current_handles = list(driver.window_handles)
        driver.execute_script("window.open(arguments[0], '_blank');", u)
        time.sleep(0.5)
        new_handles = [h for h in driver.window_handles if h not in current_handles]
        if not new_handles:
            return None
        driver.switch_to.window(new_handles[0])
        # Wait a moment for redirects to settle
        time.sleep(3.0)
        final_url = driver.current_url
        # Close the tab and go back
        driver.close()
        driver.switch_to.window(current_handles[0])
        return final_url
    except Exception:
        try:
            driver.switch_to.window(current_handles[0])
        except Exception:
            pass
        return None

def extract_facebook_ids(
    urls: List[str],
    driver=None,
    use_requests: bool = True
) -> List[Dict[str, str]]:
    out = []
    for u in urls:
        rec = {"original_url": u, "kind": "", "id": "", "final_url": ""}
       
        direct = extract_id_from_url(u)
        final_url = u

        if direct is None:
           
            final_url = None
            if use_requests:
                final_url = resolve_url_with_requests(u)
            if final_url is None and driver is not None:
                final_url = resolve_url_with_selenium(u, driver)
            if final_url is None:
               
                rec["kind"] = "unknown"
                rec["id"] = ""
                rec["final_url"] = ""
                out.append(rec)
                continue

            direct = extract_id_from_url(final_url)

        if direct:
            kind, id_str = direct
            rec["kind"] = kind
            rec["id"] = id_str
            rec["final_url"] = final_url
        else:
            rec["kind"] = "unknown"
            rec["id"] = ""
            rec["final_url"] = final_url or ""
        out.append(rec)

    return out


# --------------Example---------------

if __name__ == "__main__":
    test_urls = [
        "https://www.facebook.com/shikhwsaad1/posts/pfbid02z7JFKj8bXH1gmdrbu1m89V23gXrBfb74Qs7jGwGvqiwhg6wQo34uZp3Q1RXtQ6sBl",
        "https://www.facebook.com/watch/?v=613121104542133",
        "https://www.facebook.com/haas.fatoma/videos/1716820015534336",
        "https://www.facebook.com/photo/?fbid=24179992861588990&set=a.277160342298910",
        "https://www.facebook.com/shikhwsaad1/posts/pfbid02z7JFKj8bXH1gmdrbu1m89V23gXrBfb74Qs7jGwGvqiwhg6wQo34uZp3Q1RXtQ6sBl",
        "https://www.facebook.com/permalink.php?story_fbid=pfbid0Wt1ccwAmxftficJ5MGjW61RpxQry7J1KgPePZsxycDRyqUx2viJ5iQ4igNba5rSCl&id=61569704686235",
        "https://www.facebook.com/Ductour123/posts/pfbid02TFgrQJxWPikLSGj2j4mHHp8pcPSMLYiGrTvqbK95j3NQfZ8TRqfxNN9egVbPKDZDl",
        "https://www.facebook.com/watch/?v=3995585577393917",
        "https://www.facebook.com/reel/994171912430118",
        "https://www.facebook.com/share/p/173dWFere7/",
        "https://www.facebook.com/share/v/1B6UHzrKiZ/"
    ]

  
    results = extract_facebook_ids(test_urls, driver=None, use_requests=True)
    print(len(test_urls),len(results))
    for r in results:
        print(r['id'])

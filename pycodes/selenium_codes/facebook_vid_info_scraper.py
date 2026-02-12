from __future__ import annotations
from typing import List, Dict
import time
import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, NoSuchElementException, WebDriverException
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import re
from urllib.parse import urljoin



def _collect_candidate_text_nodes(driver) -> List[str]:
    """
    Collect likely caption text nodes for a reel.
    Strategy:
      1) Look for known 'message' containers FB often uses for authored text.
      2) Look for text blocks in the primary column (role='main') with dir='auto'
         that are not clearly comments.
    We return multiple candidates; the caller picks the best.
    """
    candidates = set()

    XPATHS = [
        # Classic authored text containers used widely by FB posts
        "//div[@data-ad-preview='message']",
        "//div[@data-ad-comet-preview='message']",
        "//*[@data-ad-preview='message']",                              # classic feed
        "//div[@role='article']//div[@dir='auto']",
        "//div[@role='article']//span[@dir='auto']",
        "//*[@role='main']//div[@dir='auto']",
        "//*[@role='main']//span[@dir='auto']",

        # Reels often show caption in the side panel on desktop; target readable blocks under main region
        # Filter out obvious comments list containers (heuristic).
        "//div[@role='main']//div[@dir='auto' and string-length(normalize-space())>0]"
        # Reels pages (caption is usually in a side pane or overlay)
        "//*[contains(@data-pagelet,'Reel') or contains(@data-pagelet,'Reels')]//div[@dir='auto']",
        "//*[contains(@data-pagelet,'Reel') or contains(@data-pagelet,'Reels')]//span[@dir='auto']"
    ]

    try:
        # Try to find the 'See More' button and click it
        see_more_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'x1i10hfl xjbqb8w x6umtig x1b1mbwd xaqea5y xav7gou x9f619 x1ypdohk xt0b8zv xzsf02u x1s688f') or text()='See more']"))
        )
        see_more_button.click()
        time.sleep(2) # Wait for content to expand
    except:
        pass # 'See More' button not found or not clickable, continue without expanding

    for xp in XPATHS:
        try:
            els = driver.find_elements(By.XPATH, xp)
            for el in els:
                try:
                    if el.is_displayed():
                        txt = el.text.strip()
                        if txt:
                            candidates.add(txt)
                except StaleElementReferenceException:
                    continue
        except WebDriverException:
            continue

    return list(candidates)

def _pick_best_caption(candidates: List[str]) -> str:
    """
    Heuristic to pick the most plausible 'main caption' text for a reel.
    - Prefer the longest non-comment-looking block.
    - Drop very short fragments or obvious UI strings.
    """
    if not candidates:
        return ""

    # Filter out very short or obviously non-caption fragments
    filtered = []
    ui_noise = {"like", "comment", "share", "follow", "subscriptions", "volgen"}
    for c in candidates:
        plain = c.strip()
        if len(plain) < 5:
            continue
        # Skip blocks that look like controls-only
        low = plain.lower()
        if any(w in low for w in ui_noise) and len(plain) < 40:
            continue
        filtered.append(plain)

    if not filtered:
        filtered = candidates

    # Pick the longest as a simple heuristic for "main caption"
    filtered.sort(key=len, reverse=True)
    return filtered[0].strip()

def scrape_facebook_vids(df: pd.DataFrame, driver, wait_seconds: int = 30) -> List[Dict[str, str]]:
    """
    Takes a DataFrame with column 'accounts' that contains only /reel/ URLs.
    For each URL:
      - opens it (assumes you're already logged in to Facebook),
      - expands any 'See more',
      - extracts the full reel caption text (author's text).
    Returns: list of dicts [{ 'url': ..., 'text': ... }, ...]
    """
    if "accounts" not in df.columns:
        raise ValueError("DataFrame must contain an 'accounts' column with /reel/ URLs.")

    out: List[Dict[str, str]] = []


    for index , row in df.iterrows():
        text = ""
        try:
            
            driver.get(row["accounts"])

            #bypass factcheck
            bypass_factcheck(driver)

            # Wait until the main region or the video container shows up – reels pages usually mount quickly.
            try:
                WebDriverWait(driver, wait_seconds).until(
                    EC.presence_of_element_located((By.XPATH, "//div[@role='main']"))
                )
            except TimeoutException:
                # Try a softer wait for any visible text block
                WebDriverWait(driver, 4).until(
                    EC.presence_of_element_located((By.XPATH, "//div[@dir='auto']"))
                )

    
            # After expansion, gather candidates for caption and pick best
            candidates = _collect_candidate_text_nodes(driver)
            text = _pick_best_caption(candidates)

        except Exception:
            # keep text = "" for this URL; continue
            pass
        
        likes, comments, shares = get_reel_counts(driver)
        print("likes: ",likes,"comments: ",comments,"shares:",shares)
        print("text: \n",text)

        name, profile_url = get_poster_name_and_url(driver)
        print("name: ",name,"profile_url: \n",profile_url)

        # print(f"news_id:{row['news_id']}\nurl:{row['accounts']}\ntext:{text}")
        out.append({"news_id":row["news_id"],"url": row["accounts"], "text": text,"like":likes,"comments":comments,"shares":shares,"username":name,"profile_url":profile_url})
        
        time.sleep(5)
    return out


_ABBREV_RE = re.compile(r"^(\d+(?:[.,]\d+)?)([KkMm])?$")

def _to_int_string(s: str) -> str:
    """Normalize '94', '1.2K', '3,456', '1.1M' -> '94', '1200', '3456', '1100000'."""
    if not s:
        return ""
    t = s.replace("\u200e","").replace("\u200f","").strip()  # remove bidi marks
    t = t.replace(",", "")
    m = _ABBREV_RE.match(t)
    if not m:
        # fallback: digits only
        digits = re.sub(r"\D", "", t)
        return digits
    val = float(m.group(1).replace(",", "."))
    suf = (m.group(2) or "").lower()
    if   suf == "k": val *= 1_000
    elif suf == "m": val *= 1_000_000
    return str(int(round(val)))

def _metric_from_button(post, label_token: str) -> str:
    """
    Find the Reel's metric button by aria-label (Like / Comment / Share),
    then grab the last non-empty <span> text inside it and normalize.
    """
    # case-insensitive contains() via translate()
    btn = post.find_element(
        By.XPATH,
        ".//div[@role='button' and @aria-label"
        f" and contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),"
        f" '{label_token.lower()}')]"
    )
    # take the last non-empty span (skips icon wrappers)
    val_el = btn.find_element(By.XPATH, ".//span[normalize-space()!=''][last()]")
    return _to_int_string(val_el.text.strip())

def get_reel_counts(post):
    likes = comments = shares = ""
    try:    likes    = _metric_from_button(post, "Like")
    except NoSuchElementException: pass
    try:    comments = _metric_from_button(post, "Comment")
    except NoSuchElementException: pass
    try:    shares   = _metric_from_button(post, "Share")
    except NoSuchElementException: pass
    return likes, comments, shares


def get_poster_name_and_url(post, base="https://www.facebook.com"):
    """
    post: the container element for the post/Reel (e.g., ancestor div with role='article' or the reel panel)
    returns: (name, absolute_profile_url)  — empty strings if not found
    """
    CANDIDATES = [
        # Typical desktop/Reels header: <h2> ... <a ...>Name</a>
        ".//h2//a[@role='link' and @href][1]",
        # Any link inside header region
        ".//h2//a[@href][1]",
        # Links with profile-like hrefs even if h2 is absent
        ".//a[@role='link' and @href and (contains(@href,'/profile.php') or contains(@href,'/people/') or contains(@href,'/pages/'))][1]",
        # Heuristic: “See owner profile” label (as in your snippet)
        ".//a[@role='link' and @aria-label and contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'owner profile')][1]",
    ]
    link = None
    for xp in CANDIDATES:
        try:
            link = post.find_element(By.XPATH, xp)
            if link.text.strip():
                break
        except NoSuchElementException:
            continue
    if not link:
        return "", ""

    name = link.text.strip()

    # Build an absolute URL if it's a site-relative href like "/profile.php?id=..."
    href = link.get_attribute("href") or ""
    if href.startswith("/"):
        href = urljoin(base, href)

    return name, href


def bypass_factcheck(driver, timeout=5):
    """
    If a fact-check overlay appears, click 'See why' then 'See post anyway'.
    Safe to call on every post open — it just skips if nothing is there.
    """
    try:
        # Step 1: 'See why'
        see_why = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//*[normalize-space()='See why' and @role='button']"
            ))
        )
        driver.execute_script("arguments[0].click();", see_why)

        # Step 2: 'See post anyway'
        see_post = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//*[normalize-space()='See post anyway' and @role='button']"
            ))
        )
        driver.execute_script("arguments[0].click();", see_post)
        print("Bypassed fact-check overlay.")

    except TimeoutException:
        # No overlay found — nothing to bypass
        pass

    #Clicks the 'Remove' cross button if it exists.
    # Safe to call on any page — does nothing if not found.
    try:
        cross_btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, "//div[@role='button' and @aria-label='Remove']"))
        )
        driver.execute_script("arguments[0].click();", cross_btn)
    
    except TimeoutException:
        # Button not found within timeout
        pass

def split_dataframe(df, chunk_size=50):
    """
    Splits a DataFrame into a list of smaller DataFrames,
    each with up to chunk_size rows.
    """
    chunks = []
    for start in range(0, len(df), chunk_size):
        end = start + chunk_size
        chunks.append(df.iloc[start:end])
    return chunks



# df = pd.DataFrame({
#     "accounts": [
#         "https://www.facebook.com/reel/994171912430118",
#         "https://www.facebook.com/reel/1303881981474509",
#         "https://www.facebook.com/reel/1395866901477614",
#         "https://www.facebook.com/reel/613876958265329",
#         "https://www.facebook.com/reel/760527776622792",
#         "https://www.facebook.com/reel/1744216886466580",
#         "https://www.facebook.com/reel/1033090205369568",
#         "https://www.facebook.com/reel/24040941122271529",
#         "https://www.facebook.com/reel/2074864809944664",
#         "https://www.facebook.com/reel/2852613701794754"

#     ],
#     "news_id":[1,2,3,4,5,6,7,8,9,10]
# })

# df = pd.DataFrame({
#     "accounts": [
#         "https://www.facebook.com/reel/1372268920761032",
#     ],
#     "news_id":[1]
# })

##--------------This block is for starting the automation------------------------
#load_dotenv()
# chrome_driver_path = os.getenv("chrome_driver_path")
# path_to_brave = os.getenv("path_to_brave")
# options = Options()
# USER_DATA_DIR = os.getenv("USER_DATA_DIR")
# PROFILE_NAME = "Profile 1"
# options.add_argument(f"--user-data-dir={USER_DATA_DIR}")
# options.add_argument(f"--profile-directory={PROFILE_NAME}")
# options.binary_location = path_to_brave
# service = Service(executable_path=chrome_driver_path)
# driver = webdriver.Chrome(service=service, options=options)


# driver.get("https://www.facebook.com/")
# print(
#     "Please log in to Facebook in the opened browser window. "
#     "After you have successfully logged in, return here and press Enter to continue."
# )
# input()

# url_df = pd.read_csv("beam_FB_vid_urls_false_check.csv")
# url_dfs = split_dataframe(url_df,chunk_size=20)

# all_results = []

# for i, df in enumerate(url_dfs, 1):
#     results = scrape_facebook_vids(df, driver)
#     result_df = pd.DataFrame(results)
#     all_results.append(result_df)
#     result_df.to_csv(f"FB_vid_info_{i}.csv",index=False,encoding="utf-8-sig")


# all_results_df = pd.concat(all_results, ignore_index=True)
# all_results_df.to_csv(f"all_FB_vid_info.csv",index=False,encoding="utf-8-sig")
##-----------------------------------------------------

# for row in results:
#     print(row["url"], "=>", row["text"])
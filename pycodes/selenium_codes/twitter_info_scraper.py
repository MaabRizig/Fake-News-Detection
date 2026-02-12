from __future__ import annotations
from typing import List, Dict
import time
import re
import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    NoSuchElementException,
    WebDriverException,
)

# ----------------------- Browser setup -----------------------
# chrome_driver_path = os.getenv("chrome_driver_path")
# path_to_brave = os.getenv("path_to_brave")
# USER_DATA_DIR = os.getenv("USER_DATA_DIR")
# PROFILE_NAME = "Profile 1"

# options = Options()
# options.binary_location = path_to_brave
# options.add_argument(f"--user-data-dir={USER_DATA_DIR}")
# options.add_argument(f"--profile-directory={PROFILE_NAME}")
# # options.add_argument("--headless=new")  # uncomment if you want headless
# # options.add_argument("--window-size=1280,1000")

# service = Service(executable_path=chrome_driver_path)
# driver = webdriver.Chrome(service=service, options=options)

##----------------------------------------

WAIT_SHORT = 10
WAIT_LONG = 20

def safe_text(el) -> str | None:
    try:
        t = el.text
        return t if t is not None and t.strip() != "" else None
    except Exception:
        return None

def get_first_article(driver) -> object | None:
    try:
        WebDriverWait(driver, WAIT_LONG).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'article[data-testid="tweet"]'))
        )
        return driver.find_element(By.CSS_SELECTOR, 'article[data-testid="tweet"]')
    except TimeoutException:
        return None

def scrape_tweets(df: pd.DataFrame, driver) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []

    for index, row in df.iterrows():
        url = row.get("accounts")
        news_id = row.get("news_id")

        if not isinstance(url, str) or not url.strip():
            out.append({
                "news_id": news_id,
                "tweet_link": url,
                "username_link": None,
                "username": None,
                "text": None,
                "engagement_text": None,
                "image_link": None
            })
            continue

        driver.get(url)

        # Wait for page JS to settle a bit
        time.sleep(1.0)

        tweet_article = get_first_article(driver)
        if not tweet_article:
            out.append({
                "news_id": news_id,
                "tweet_link": url,
                "username_link": None,
                "username": None,
                "text": None,
                "engagement_text": None,
                "image_link": None
            })
            continue

        # -------- Username / link --------
        username_link = None
        username = None
        try:
            user_anchor = WebDriverWait(tweet_article, WAIT_SHORT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="User-Name"] a'))
            )
            username_link = user_anchor.get_attribute("href")
            username = safe_text(user_anchor)
        except (TimeoutException, NoSuchElementException, StaleElementReferenceException):
            pass

        # -------- Tweet text (Arabic-first, then fallback any language) --------
        text = None
        try:
            # Arabic-specific
            text_div = tweet_article.find_element(By.CSS_SELECTOR, 'div[dir="auto"][data-testid="tweetText"][lang="ar"]')
            text = safe_text(text_div)
        except NoSuchElementException:
            # Fallback without lang filter (any language)
            try:
                text_div = tweet_article.find_element(By.CSS_SELECTOR, 'div[dir="auto"][data-testid="tweetText"]')
                text = safe_text(text_div)
            except NoSuchElementException:
                text_div = None

        # -------- Engagement (retweet button -> nearest ancestor with aria-label) --------
        engagement_text = None
        try:
            retweet_btn = tweet_article.find_element(By.CSS_SELECTOR, 'button[data-testid="retweet"]')
            # Try nearest ancestor with aria-label (up to a few levels)
            ancestor_xpath_candidates = [
                "./ancestor::*[@aria-label][1]",
                "./ancestor::div[@aria-label][1]",
                "./ancestor::*[@role='group'][@aria-label][1]",
            ]
            parent_with_aria = None
            for xp in ancestor_xpath_candidates:
                try:
                    parent_with_aria = retweet_btn.find_element(By.XPATH, xp)
                    if parent_with_aria:
                        break
                except NoSuchElementException:
                    continue

            if parent_with_aria:
                engagement_text = parent_with_aria.get_attribute("aria-label")
        except NoSuchElementException:
            pass

        # -------- Image link --------
        image_link = None
        try:
            img = tweet_article.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetPhoto"] img')
            image_link = img.get_attribute("src")
        except:
            pass

        out.append({
            "news_id": news_id,
            "tweet_link": url,
            "username_link": username_link,
            "username": username,
            "text": text,
            "engagement_text": engagement_text,
            "image_link": image_link
        })
        print({
            "news_id": news_id,
            "tweet_link": url,
            "username_link": username_link,
            "username": username,
            "text": text,
            "engagement_text": engagement_text,
            "image_link": image_link
        })

        time.sleep(5)

    return out

def split_dataframe(df, chunk_size=50):
    chunks = []
    for start in range(0, len(df), chunk_size):
        end = start + chunk_size
        chunks.append(df.iloc[start:end])
    return chunks

# -----------------------

# url_df = pd.read_csv("beam_twitter_accounts_info.csv")
# url_dfs = split_dataframe(url_df, chunk_size=20)
# sub_url_dfs = url_dfs[3:]
# all_results = []

# for i, subdf in enumerate(sub_url_dfs, 4):
#     results = scrape_tweets(subdf, driver)
#     result_df = pd.DataFrame(results)
#     all_results.append(result_df)
#     result_df.to_csv(f"Twitter_info_{i}.csv", index=False, encoding="utf-8-sig")

# all_results_df = pd.concat(all_results, ignore_index=True)
# all_results_df.to_csv("all_Twitter_info.csv", index=False, encoding="utf-8-sig")

# driver.quit()
##-----------------------------

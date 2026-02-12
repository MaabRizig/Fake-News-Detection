from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

from typing import List, Dict
import re
import time
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException, JavascriptException, WebDriverException
import pandas as pd
from dotenv import load_dotenv

def _to_int(text: str) -> int | None:
    if not text:
        return None
    # normalize Arabic-Indic digits if present, then strip non-digits
    norm = text.translate(_ARABIC_INDIC)
    m = re.findall(r"\d+", norm)
    return int(m[0]) if m else None

def extract_engagement_counts_from_block(driver, post_root):

    toolbar = post_root.find_element(
        By.XPATH,
        ".//*[(@role='toolbar' or @role='group') and contains(@aria-label,'See who reacted')]"
    )

    reactions_total = None
    try:
        toolbar_text = toolbar.text or ""
        number_nodes = toolbar.find_elements(By.XPATH, ".//span|.//div")
        texts = [toolbar_text]
        for n in number_nodes:
            try:
                t = (n.text or "").strip()
                if t:
                    texts.append(t)
            except StaleElementReferenceException:
                continue
        nums = []
        for t in texts:
            t_norm = t.translate(_ARABIC_INDIC)
            nums += [int(x) for x in re.findall(r"\d+", t_norm)]
        if nums:
            reactions_total = max(nums)
    except Exception:
        reactions_total = None

    # COMMENTS & SHARES: the next two count buttons after the toolbar.We look for two following clickable blocks that contain a numeric span.
    
    comments_total, shares_total = None, None
    try:
        # Limit the search to a nearby ancestor to avoid wandering into other page areas
        # Start from the toolbar's closest container; then look forward for two buttons with digits
        container = toolbar.find_element(By.XPATH, "./ancestor::div[1]")
        count_buttons = container.find_elements(
            By.XPATH,
            "following::div[@role='button'][.//span[normalize-space()!='']]"
        )

        # Collect numeric spans from the first few candidate buttons
        found_counts = []
        for btn in count_buttons[:6]:  # small window is enough
            # try to find a nested span whose text is purely numeric
            spans = btn.find_elements(By.XPATH, ".//span[normalize-space()!='']")
            for sp in spans:
                val = _to_int(sp.text.strip())
                if val is not None:
                    found_counts.append(val)
                    break  # one number per button is enough
            if len(found_counts) >= 2:
                break

        if found_counts:
            comments_total = found_counts[0]  # first button number after toolbar
            if len(found_counts) > 1:
                shares_total = found_counts[1]  # second button number after toolbar
    except NoSuchElementException:
        pass

    return reactions_total, comments_total, shares_total

def extract_text(driver):

    try:
        target_div = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//div[contains(@class,'xyinxu5') and contains(@class,'xyri2b') and contains(@class,'x1g2khh7') and contains(@class,'x1c1uobl')]"
            ))
        )

        try:
            see_more_button = WebDriverWait(driver, 3).until( EC.element_to_be_clickable(
                (By.XPATH, "//div[contains(@class, 'xxyinxu5 xyri2b x1g2khh7 x1c1uobl') or text()='See more']"))
                )
            see_more_button.click()
            time.sleep(2)
        
        except:
            pass
        text = target_div.text.strip()
        return text if text else None

    except Exception:
        return None

_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

def _nums(text: str):
    if not text:
        return []
    t = text.translate(_ARABIC_INDIC)
    return [int(x) for x in re.findall(r"\d+", t)]

def _rect(driver, el):
    return driver.execute_script(
        "const r = arguments[0].getBoundingClientRect();"
        "return {x:(r.left+r.right)/2, top:r.top, bottom:r.bottom, left:r.left, right:r.right};",
        el
    )

def _find_engagement_container(driver):
    # Find the toolbar first, then climb to its nearest engagement container
    toolbar = driver.find_element(
        By.XPATH,
        "//*[(@role='toolbar' or @role='group') and "
        "(contains(@aria-label,'See who reacted to this') or contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'reacted'))]"
    )
    try:
        return toolbar.find_element(By.XPATH, "ancestor::div[contains(@class,'x1n2onr6')][1]")
    except NoSuchElementException:
        # fallback: just return the toolbar's immediate parent
        return toolbar.find_element(By.XPATH, "./ancestor::div[1]")



def capture_likes_block_text(driver):
    """
    Returns the text from the parent <div> of the first
    <span aria-label="See who reacted to this">, or None if not present.
    """
    try:
        # 1) first matching span
        span = driver.find_element(
            By.XPATH,
            "(//span[@aria-label='See who reacted to this'])[1]"
        )

        # 2) its nearest parent div
        parent_div = span.find_element(By.XPATH, "ancestor::div[1]")

        # 3) the text in that parent block
        txt = (parent_div.text or "").strip()
        return txt if txt else None

    except NoSuchElementException:
        return None

def _pick_number_relative_to_icon(driver, btn, side: str):
    """
    side='left'  -> choose numeric span LEFT of icon (comments)
    side='right' -> choose numeric span RIGHT of icon (shares)
    """
    try:
        icon = btn.find_element(By.XPATH, ".//i[@data-visualcompletion='css-img']")
        icon_x = _rect(driver, icon)["x"]
    except Exception:
        nums = _nums(btn.text)
        return nums[0] if nums else None

    spans = btn.find_elements(By.XPATH, ".//span[normalize-space()!='']")
    for sp in spans:
        try:
            vals = _nums(sp.text.strip())
            if not vals:
                continue
            x = _rect(driver, sp)["x"]
            if side == "left" and x < icon_x:
                return vals[0]
            if side == "right" and x > icon_x:
                return vals[0]
        except (StaleElementReferenceException, JavascriptException):
            continue

    # Fallback: first number within the button
    nums = _nums(btn.text)
    return nums[0] if nums else None

def extract_likes_comments_shares(driver):
    """
    Returns (likes_total, comments_total, shares_total) from the post's engagement block:
      - Likes: in/after the 'See who reacted to this' toolbar (prefers 'All reactions', otherwise sums per-type)
      - Comments: number left of the comment icon
      - Shares:   number right of the share icon
    If any element is missing, the corresponding value is None.
    """
    likes_total = comments_total = shares_total = None

    try:
        eng = _find_engagement_container(driver)
    except Exception:
        return likes_total, comments_total, shares_total

    # Toolbar
    toolbar = None
    try:
        toolbar = eng.find_element(
            By.XPATH,
            ".//*[(@role='toolbar' or @role='group') "
            "and (contains(@aria-label,'See who reacted to this') "
            "or contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'reacted'))]"
        )
    except NoSuchElementException:
        pass

    # Likes
    try:
        if toolbar is not None:
            likes_total = capture_likes_block_text(toolbar)
    except Exception:
        likes_total = None

    # Comments & shares
    buttons = []
    try:
        buttons = eng.find_elements(By.XPATH, ".//div[@role='button'][.//i[@data-visualcompletion='css-img']]")
        buttons = [b for b in buttons if b.is_displayed()][:2]
    except Exception:
        buttons = []

    try:
        if len(buttons) >= 1:
            comments_total = _pick_number_relative_to_icon(driver, buttons[0], side="left")
        if len(buttons) >= 2:
            shares_total = _pick_number_relative_to_icon(driver, buttons[1], side="right")

        # Fallbacks if still None
        if comments_total is None and buttons:
            comments_total = (_pick_number_relative_to_icon(driver, buttons[0], side="left")
                              or _pick_number_relative_to_icon(driver, buttons[0], side="right"))
        if shares_total is None and len(buttons) >= 2:
            shares_total = (_pick_number_relative_to_icon(driver, buttons[1], side="right")
                            or _pick_number_relative_to_icon(driver, buttons[1], side="left"))
    except Exception:
        pass

    return likes_total, comments_total, shares_total

def get_username_and_profile_selenium(scope):
    """
    `scope` is a WebElement (e.g., the post container, or the whole driver).
    Returns (username, userprofile) or (None, None) if not found.
    """
    try:
        # Find a div that has BOTH classes, regardless of order
        user_div = scope.find_element(
            By.XPATH,
            ".//div[contains(@class,'xu06os2') and contains(@class,'x1ok221b')]"
        )
    except NoSuchElementException:
        return None, None

    # Username text
    username = (user_div.text or "").strip() or None

    # First <a> inside that div -> profile URL
    try:
        a = user_div.find_element(By.XPATH, ".//a[1]")
        userprofile = a.get_attribute("href")
        # sometimes FB puts relative hrefs like /profile.php?id=...
        # normalize to absolute if you want:
        # if userprofile and userprofile.startswith("/"):
        #  userprofile = "https://www.facebook.com" + userprofile
    except NoSuchElementException:
        userprofile = None

    return username, userprofile

def open_img(driver, timeout=5) -> bool:
    """
    Find the 2nd <div role="dialog"> on the page.
    Inside it, find an <a> that wraps an <img> and navigate to its href in the same tab.
    If no <a> is found but an <img> exists, fall back to opening the <img src>.
    If any step is missing, return False without raising.

    Returns True if navigation happened, else False.
    """
    try:
        # the second dialog (1-based indexing in XPath)
        dialog = driver.find_element(By.XPATH, "(//div[@role='dialog'])[2]")
    except NoSuchElementException:
        return False

    # try to find a link that contains an image
    try:
        link = dialog.find_element(By.XPATH, ".//a[.//img[@src]]")
        href = link.get_attribute("href")
        if href:
            driver.get(href)
            return True
    except (NoSuchElementException, StaleElementReferenceException):
        pass

    # fallback: if there's an <img> but no wrapping <a>, open the image src
    try:
        img = dialog.find_element(By.XPATH, ".//img[@src]")
        src = img.get_attribute("src")
        if src:
            driver.get(src)
            return True
    except (NoSuchElementException, StaleElementReferenceException):
        pass

    # nothing usable found
    return False

def bypass_factcheck(driver, timeout=3):
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

def get_post_image_src(driver, timeout=3):
    """
    Return the 'src' attribute of the first post image if it exists.
    Otherwise return None.
    """
    try:
        img = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//img[@data-visualcompletion='media-vc-image']"
            ))
        )
        return img.get_attribute("src")
    except TimeoutException:
        return None

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



def scrape_facebook_posts(df,driver):

    if "accounts" not in df.columns:
        raise ValueError("DataFrame must contain an 'accounts' column with post URLs.")

    out: List[Dict[str, str]] = []

    for index , row in df.iterrows():
        try:
            driver.get(row["accounts"])
        except:
            print("error: ERR_NAME_NOT_RESOLVED")
            result = {
            "news_id":row["news_id"],
            "url":row["accounts"],
            "text": "ERR_NAME_NOT_RESOLVED",
            "like":None,
            "comments":None,
            "shares": None,
            "username":None,
            "profile_url": None,
            "image_src": None
            }
            out.append(result)
            continue

        bypass_factcheck(driver)
        open_img(driver)
        bypass_factcheck(driver)

        text = extract_text(driver)
        likes, comments, shares = extract_likes_comments_shares(driver)
        username, profile = get_username_and_profile_selenium(driver)
        image_src = get_post_image_src(driver)
        result = {
            "news_id":row["news_id"],
            "url":row["accounts"],
            "text":text,
            "like":likes,
            "comments":comments,
            "shares": shares,
            "username":username,
            "profile_url": profile,
            "image_src": image_src
        }
        print(result)
        out.append(result)
        time.sleep(5)
    return out


# #--------------This block is for starting the automation------------------------
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

# url_df = pd.read_csv("Misbar_FB_posts_urls.csv")

# url_dfs = split_dataframe(url_df,chunk_size=20)

# all_results = []

# for i, df in enumerate(url_dfs, 1):
#     results = scrape_facebook_posts(df, driver)
#     result_df = pd.DataFrame(results)
#     all_results.append(result_df)
#     result_df.to_csv(f"FB_posts_info_{i}.csv",index=False,encoding="utf-8-sig")


# all_results_df = pd.concat(all_results, ignore_index=True)
# all_results_df.to_csv(f"all_FB_posts_info.csv",index=False,encoding="utf-8-sig")


# driver.quit()
# #------------------------------------------------------


# url_list = [
#     "https://www.facebook.com/groups/2486356218255694/permalink/5143295975895025/?rdid=jf5PMWbz4Eun6ILD#",
#     "https://www.facebook.com/Ductour123/posts/pfbid02TFgrQJxWPikLSGj2j4mHHp8pcPSMLYiGrTvqbK95j3NQfZ8TRqfxNN9egVbPKDZDl",
#     "https://www.facebook.com/photo/?fbid=936674068672820&set=a.260234232983477",
#     "https://www.facebook.com/photo?fbid=964971728966459&set=pb.100063609225380.-2207520000",
#     "https://www.facebook.com/photo?fbid=964971728966459&set=pb.100063609225380.-2207520000",
#     "https://www.facebook.com/photo?fbid=965515565375968&set=a.482586970335499",
#     "https://www.facebook.com/Shafataedu/posts/1204472595014202",
#     "https://www.facebook.com/share/p/19Y9wiX1VW/",
#     "https://www.facebook.com/Ductour123/posts/pfbid02TFgrQJxWPikLSGj2j4mHHp8pcPSMLYiGrTvqbK95j3NQfZ8TRqfxNN9egVbPKDZDl"    
# ]


# url_df = pd.DataFrame({"news_id":[313,314],"accounts":[
#     "https://www.facebook.com/permalink.php?story_fbid=pfbid03575R9Y7PbhwrrJCFV9qd7tVsof8yeVXnVDKy9zQgQnSUeohHmYkz5K3Gz2w7fVXZl&id=61551757785646&__cft__[0]=AZV8ZQ24g_ncxVObRvGwNv2aMFM5yvvVTFSZkDYVfjk3rK5sQpC38AbKHxLXYOOzo8tOhPB-7YP4PClpmvyWv-zMJmjFS13Ms2sy16HdSkFqnVu1bHz25XJNFUuMZCebHqwq7cyOl-ROIWHfeI-Tyc235MF3PgFE4tQfmq_R66jE3A&__tn__=%2CO%2CP-R",
#     "http://.facebook.com/photo/?fbid=1001868844635922&set=pb.100044384475694.-2207520000"
# ]})
import pandas as pd
#from scrape_accounts.return_post_id import extract_facebook_ids


def classify_fb_urls(df: pd.DataFrame):
    """
    Classify Facebook URLs into videos vs posts.
    
    Args:
        df (pd.DataFrame): must contain columns ['accounts', 'news_id']
    
    Returns:
        video_urls (list of tuples): [(url, news_id), ...]
        post_urls (list of tuples): [(url, news_id), ...]
    """
    video_patterns = ["watch/?v=", "/videos/", "/reel/","/v/","/r/"]

    video_urls = []
    post_urls = []

    for _, row in df.iterrows():
        url = str(row["accounts"])
        news_id = row["news_id"]

        if any(pat in url for pat in video_patterns):
            video_urls.append((url, news_id))
        else:
            post_urls.append((url, news_id))

    return video_urls, post_urls


# test_urls = [
#     "https://www.facebook.com/shikhwsaad1/posts/pfbid02z7JFKj8bXH1gmdrbu1m89V23gXrBfb74Qs7jGwGvqiwhg6wQo34uZp3Q1RXtQ6sBl",
#     "https://www.facebook.com/watch/?v=613121104542133",
#     "https://www.facebook.com/haas.fatoma/videos/1716820015534336",
#     "https://www.facebook.com/photo/?fbid=24179992861588990&set=a.277160342298910",
#     "https://www.facebook.com/shikhwsaad1/posts/pfbid02z7JFKj8bXH1gmdrbu1m89V23gXrBfb74Qs7jGwGvqiwhg6wQo34uZp3Q1RXtQ6sBl",
#     "https://www.facebook.com/permalink.php?story_fbid=pfbid0Wt1ccwAmxftficJ5MGjW61RpxQry7J1KgPePZsxycDRyqUx2viJ5iQ4igNba5rSCl&id=61569704686235",
#     "https://www.facebook.com/Ductour123/posts/pfbid02TFgrQJxWPikLSGj2j4mHHp8pcPSMLYiGrTvqbK95j3NQfZ8TRqfxNN9egVbPKDZDl",
#     "https://www.facebook.com/watch/?v=3995585577393917",
#     "https://www.facebook.com/reel/994171912430118",
#     "https://www.facebook.com/share/p/173dWFere7/",
#     "https://www.facebook.com/share/v/1B6UHzrKiZ/"
# ]

# from selenium.webdriver.chrome.service import Service
# from selenium.webdriver.chrome.options import Options
# from selenium import webdriver
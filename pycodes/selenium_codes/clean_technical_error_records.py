import pandas as pd

info_df = pd.read_csv("all_FB_vid_info.csv")


# records with tech error
condition = info_df["text"]  == "This may be because of a technical error that we're working to fix. Please try reloading this page."

filter_df = info_df[~ condition]

filter_df.to_csv("beam_FB_vid_urls_filtered.csv",index=False,encoding="utf-8-sig")

error_df = info_df[condition]
error_df = error_df[["news_id","url"]]

error_df = error_df.rename(columns={"url":"accounts"})
error_df.to_csv("beam_FB_vid_urls_error.csv",index=False,encoding="utf-8-sig")

# records with false check
condition = info_df["text"] == "Partly false. Reviewed by third-party fact-checkers."
check_false_df = info_df[condition]
check_false_df = check_false_df[["news_id","url"]]
check_false_df = check_false_df.rename(columns={"url":"accounts"})

check_false_df.to_csv("beam_FB_vid_urls_false_check.csv",index=False,encoding="utf-8-sig")

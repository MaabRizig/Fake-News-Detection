import pandas as pd

dfs = []
for i in range(1,5):
    df = pd.read_csv(f"FB_posts_info_{i}.csv")
    dfs.append(df)


all_files_df = pd.concat(dfs,ignore_index=True)

print("number of rows: ",all_files_df.shape[0])

original_df = pd.read_csv("Misbar_FB_posts_urls.csv")

print("acuall number of rows: ",original_df.shape[0])

#check if all links are proccessed and in the same order

condition = all_files_df["url"] == original_df["accounts"]
print(sum(condition))
conditoin = all_files_df["news_id"] == original_df["news_id"]
print(sum(conditoin))

all_files_df.to_csv("all_FB_posts_info.csv",index=False,encoding='utf-8-sig')

post_df = pd.read_csv("all_FB_posts_info.csv")


condition = (post_df["text"].isna()) | (post_df["text"] == "")

print("number of unusefull rows: ",sum(condition))

no_text_df = post_df[condition]
no_text_df.to_csv("FB_posts_no_text.csv",index=False,encoding="utf-8-sig")


with_text_df = post_df[~ condition]

with_text_df.to_csv("Misbar_all_FB_posts_info_1.csv",index=False,encoding="utf-8-sig")

# # records with no text , but has a collected reaction. these records will propaply has an image contain the desired news

condition = ~ no_text_df["like"].isna() | ~ no_text_df["comments"].isna() | ~ no_text_df["shares"].isna()

print("records without text but has a reaction:",sum(condition))

no_text_yes_reaction_df = no_text_df[condition]

no_text_yes_reaction_df.to_csv("no_text_yes_reaction_probably_images_news.csv",index=False,encoding="utf-8-sig")

# # records with text



# def split_by_idx(df,idx):
#     part_df = df.iloc[:idx]
#     return part_df

# # print("with image and without text",no_text_df.shape[0]-sum(condition))

# df = pd.read_csv("beam_FB_post_urls.csv")

# part_df = df.iloc[520:620]
# part_df.to_csv("beam_FB_post_url_from_idx_520_to_619.csv",index=False,encoding="utf-8-sig")
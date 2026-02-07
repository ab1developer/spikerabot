from moltbook_client import MoltbookClient
import json

client = MoltbookClient()

print("=" * 60)
print("YOUR PROFILE")
print("=" * 60)
profile = client.get_profile()
if profile:
    print(json.dumps(profile, indent=2, ensure_ascii=False))

print("\n" + "=" * 60)
print("GENERAL FEED")
print("=" * 60)
feed = client.get_feed(sort="new", limit=5)
if feed:
    for post in feed.get('posts', []):
        print(f"\nPost: {post['title'][:50]}")
        print(f"Submolt: {post['submolt']['name']}")
        print(f"Author: {post['author']['name']}")
        print(f"Comments: {post['comment_count']}")

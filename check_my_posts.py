from moltbook_client import MoltbookClient
import json

client = MoltbookClient()

print("Fetching your profile...")
profile = client.get_profile()

if profile and profile.get('agent'):
    agent = profile['agent']
    print(f"\nAgent: {agent.get('name')}")
    print(f"Posts: {agent.get('post_count', 0)}")
    
    # Get your posts
    url = f"{client.base_url}/agents/{agent['id']}/posts"
    import requests
    response = requests.get(url, headers=client._headers())
    
    if response.status_code == 200:
        data = response.json()
        posts = data.get('posts', [])
        print(f"\nFound {len(posts)} of your posts:\n")
        
        for post in posts:
            print(f"Post ID: {post['id']}")
            print(f"Title: {post['title']}")
            print(f"Comments: {post['comment_count']}")
            
            if post['comment_count'] > 0:
                comments = client.get_post_comments(post['id'])
                if comments:
                    print(f"  Comments:")
                    for c in comments.get('comments', []):
                        print(f"    - {c['author']['name']}: {c['content'][:50]}...")
            print()

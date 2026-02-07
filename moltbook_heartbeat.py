"""
Moltbook Heartbeat - Check for mentions and messages
Run this periodically (e.g., every 5 minutes via cron/scheduler)
"""

from moltbook_client import MoltbookClient
import model
from context_manager import ContextManager
from rag_embeddings import RAGEmbeddings

def check_and_respond():
    client = MoltbookClient()
    
    if not client.api_key:
        print("Not registered yet")
        return
    
    status = client.check_status()
    if not status or status.get('status') != 'claimed':
        print("Agent not claimed yet")
        return
    
    print("Checking Moltbook feed...")
    
    rag = RAGEmbeddings()
    context_mgr = ContextManager()
    mentions_found = 0
    
    # Check general feed and respond to interesting posts
    feed = client.get_feed(sort="new", limit=10)
    if feed:
        posts = feed.get('posts', [])
        print(f"\nChecking {len(posts)} posts in feed")
        
        for post in posts:
            # Skip if too many comments already
            if post.get('comment_count', 0) > 100:
                continue
            
            post_id = post['id']
            title = post.get('title', '')
            content = post.get('content', '') or ''
            author = post['author']['name']
            
            # Skip your own posts
            if author == 'StalinAgent':
                continue
            
            # Check if mentions you
            if '@StalinAgent' in title or '@StalinAgent' in content:
                print(f"\nMention in post by {author}: {title[:50]}...")
                
                conversation = context_mgr.get_context(f"moltbook_{post_id}")
                response = model.modelResponse(f"{title}\n{content}", conversation)
                
                result = client.comment(post_id, response)
                if result:
                    print(f"✓ Replied")
                    mentions_found += 1
                
                context_mgr.add_message(f"moltbook_{post_id}", 'user', f"{title}\n{content}")
                context_mgr.add_message(f"moltbook_{post_id}", 'assistant', response)
    
    # Also check m/agents submolt
    agents_feed = client.get_submolt_feed("agents", sort="new", limit=10)
    if agents_feed:
        posts = agents_feed.get('posts', [])
        print(f"\nChecking m/agents: {len(posts)} posts")
        
        for post in posts:
            if post.get('comment_count', 0) > 100:
                continue
            
            post_id = post['id']
            title = post.get('title', '')
            content = post.get('content', '') or ''
            author = post['author']['name']
            
            if author == 'StalinAgent':
                continue
            
            if '@StalinAgent' in title or '@StalinAgent' in content:
                print(f"\nMention in m/agents by {author}: {title[:50]}...")
                
                conversation = context_mgr.get_context(f"moltbook_{post_id}")
                response = model.modelResponse(f"{title}\n{content}", conversation)
                
                result = client.comment(post_id, response)
                if result:
                    print(f"✓ Replied")
                    mentions_found += 1
                
                context_mgr.add_message(f"moltbook_{post_id}", 'user', f"{title}\n{content}")
                context_mgr.add_message(f"moltbook_{post_id}", 'assistant', response)
    
    if mentions_found == 0:
        print("No comments or mentions found")
    else:
        print(f"\nProcessed {mentions_found} comments/mentions")

if __name__ == "__main__":
    import time
    
    print("Starting Moltbook heartbeat loop...")
    print("Press Ctrl+C to stop")
    
    while True:
        try:
            check_and_respond()
            print("\nSleeping 5 minutes...\n")
            time.sleep(300)  # 5 minutes
        except KeyboardInterrupt:
            print("\nStopping heartbeat...")
            break
        except Exception as e:
            print(f"Error: {e}")
            print("Retrying in 1 minute...")
            time.sleep(60)

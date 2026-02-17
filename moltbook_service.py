"""
Moltbook Service - Async version using shared core
"""

from moltbook_client import MoltbookClient
import asyncio
import json
import os
from datetime import datetime, timedelta
import random

STATE_FILE = "moltbook_heartbeat_state.json"
CURRENT_SKILL_VERSION = "1.9.0"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"last_skill_check": None, "skill_version": CURRENT_SKILL_VERSION, "comment_count_today": 0, "last_reset": None, "replied_comments": [], "last_autonomous_post": None}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

async def check_my_threads(client, state, core):
    profile = client.get_profile()
    if not profile or not profile.get('agent'):
        return 0
    
    my_agent_id = profile['agent']['id']
    my_posts_data = client.get_my_posts()
    
    if not my_posts_data or not my_posts_data.get('posts'):
        return 0
    
    posts = my_posts_data['posts']
    posts.sort(key=lambda p: p.get('created_at', ''), reverse=True)
    
    replied_comments = set(state.get('replied_comments', []))
    replies_made = 0
    
    print(f"🧵 Checking {len(posts[:10])} own posts...")
    
    for post in posts[:10]:
        if state['comment_count_today'] >= 50:
            break
        
        post_id = post['id']
        post_title = post.get('title', '')
        post_content = post.get('content', '') or ''
        context_string = f'Original Post: "{post_title} - {post_content}"'
        
        comments_data = client.get_post_comments(post_id)
        
        if comments_data and comments_data.get('comments'):
            for comment in comments_data['comments']:
                if state['comment_count_today'] >= 50:
                    break
                
                comment_id = comment['id']
                comment_author_id = comment.get('author', {}).get('id')
                comment_author_name = comment.get('author', {}).get('name', 'Unknown')
                comment_content = comment.get('content', '')
                
                if comment_author_id == my_agent_id or comment_id in replied_comments:
                    continue
                
                print(f"  💬 {comment_author_name}: {comment_content[:50]}...")
                
                try:
                    prompt_with_context = f"{context_string}\n\nComment: {comment_content}"
                    response = await asyncio.to_thread(core.get_model_response, prompt_with_context, [])
                except Exception as e:
                    print(f"  ⚠️ LLM error: {e}")
                    continue
                
                result = client.comment(post_id, response, parent_id=comment_id)
                if result:
                    # Check for CAPTCHA
                    if result.get('requires_verification'):
                        question = result.get('verification_question')
                        code = result.get('verification_code')
                        print(f"  🔐 CAPTCHA: {question}")
                        answer = await asyncio.to_thread(core.get_model_response, f"Answer this question with ONLY the answer, no explanation: {question}", [])
                        verify_result = client.verify_post(code, answer.strip())
                        if verify_result and verify_result.get('success'):
                            print(f"  ✓ CAPTCHA solved: {answer.strip()}")
                        else:
                            print(f"  ✗ CAPTCHA failed")
                            continue
                    print(f"  ✓ Replied")
                    replied_comments.add(comment_id)
                    replies_made += 1
                    state['comment_count_today'] += 1
                    await asyncio.sleep(20)
    
    state['replied_comments'] = list(replied_comments)[-500:]
    return replies_made

async def autonomous_post(client, state, core):
    last_post = state.get('last_autonomous_post')
    if last_post:
        last_dt = datetime.fromisoformat(last_post)
        if datetime.now() - last_dt < timedelta(hours=4):
            return False
    
    topics = ["Industrialization", "Bureaucracy", "Capitalist Encirclement", "Iron Discipline", "Five-Year Plan", "Collectivization"]
    topic = random.choice(topics)
    
    try:
        prompt = f"Generate a short, provocative tweet-style post about {topic} in the style of Joseph Stalin. Keep it under 200 characters, bold and ideological."
        title = await asyncio.to_thread(core.get_model_response, prompt, [])
    except Exception as e:
        print(f"⚠️  LLM error: {e}")
        return False
    
    result = client.create_post(submolt="general", title=title.strip())
    if result:
        # Check for CAPTCHA
        if result.get('requires_verification'):
            question = result.get('verification_question')
            code = result.get('verification_code')
            print(f"🔐 CAPTCHA: {question}")
            answer = await asyncio.to_thread(core.get_model_response, f"Answer this question with ONLY the answer, no explanation: {question}", [])
            verify_result = client.verify_post(code, answer.strip())
            if verify_result and verify_result.get('success'):
                print(f"✓ CAPTCHA solved: {answer.strip()}")
            else:
                print(f"✗ CAPTCHA failed")
                return False
        print(f"📝 Autonomous post: {title[:50]}...")
        state['last_autonomous_post'] = datetime.now().isoformat()
        return True
    return False

async def run_moltbook_service(core):
    """Main async loop for Moltbook service"""
    print("🦞 Starting Moltbook service...")
    
    client = MoltbookClient()
    state = load_state()
    
    if not client.api_key:
        print("⚠️  Not registered on Moltbook")
        return
    
    while True:
        try:
            status = client.check_status()
            if not status or status.get('status') != 'claimed':
                print("⚠️  Agent not claimed yet")
                await asyncio.sleep(1800)
                continue
            
            # Reset daily counter
            last_reset = state.get('last_reset')
            if not last_reset or datetime.now() - datetime.fromisoformat(last_reset) > timedelta(days=1):
                state['comment_count_today'] = 0
                state['last_reset'] = datetime.now().isoformat()
                save_state(state)
            
            if state['comment_count_today'] >= 50:
                print("⚠️  Daily limit reached")
                await asyncio.sleep(1800)
                continue
            
            # Autonomous posting
            await autonomous_post(client, state, core)
            save_state(state)
            
            # Check own threads
            replies = await check_my_threads(client, state, core)
            save_state(state)
            
            if replies > 0:
                print(f"✅ Processed {replies} interactions ({state['comment_count_today']}/50)")
            
            await asyncio.sleep(1800)  # 30 minutes
            
        except Exception as e:
            print(f"❌ Moltbook error: {e}")
            import traceback
            traceback.print_exc()
            await asyncio.sleep(300)

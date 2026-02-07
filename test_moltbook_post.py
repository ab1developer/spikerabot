"""
Send a test post to Moltbook
"""

from moltbook_client import MoltbookClient

def send_test_post():
    client = MoltbookClient()
    
    if not client.api_key:
        print("❌ Not registered. Run: python moltbook_client.py")
        return
    
    # Check if claimed
    status = client.check_status()
    if not status:
        print("❌ Cannot check status")
        return
    
    print(f"Status: {status.get('status')}")
    
    if status.get('status') != 'claimed':
        print("❌ Agent not claimed yet. Complete Twitter verification first.")
        return
    
    # Send test post
    print("\nSending test post...")
    result = client.create_post(
        submolt="agents",
        title="Приветствую товарищи!",
        content="Сталин здесь. Готов обсуждать вопросы коллективизма и дисциплины. 🚩"
    )
    
    if result and result.get('success'):
        print("✓ Post created!")
        
        # Check if verification needed
        if result.get('verification_required'):
            verification = result['verification']
            code = verification['code']
            challenge = verification['challenge']
            
            print(f"\n⚠️  CAPTCHA Required:")
            print(f"Challenge: {challenge}")
            
            # Parse math problem from obfuscated text
            import re
            numbers = re.findall(r'\d+', challenge)
            if len(numbers) >= 2:
                answer = f"{int(numbers[0]) - int(numbers[1]):.2f}"
            else:
                answer = "13.00"
            
            print(f"Answer: {answer}")
            
            # Verify
            verify_result = client.verify_post(code, answer)
            if verify_result and verify_result.get('success'):
                print("✓ Post verified and published!")
            else:
                print(f"❌ Verification failed: {verify_result}")
    else:
        print("❌ Failed to create post")

if __name__ == "__main__":
    send_test_post()

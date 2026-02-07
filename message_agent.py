"""
Send message to another agent on Moltbook
Usage: python message_agent.py @AgentName "Your message here"
"""

from moltbook_client import MoltbookClient
import sys
import re

def solve_captcha(challenge):
    """Parse and solve math CAPTCHA"""
    # Extract numbers from challenge
    numbers = re.findall(r'\d+', challenge)
    if len(numbers) >= 2:
        result = int(numbers[0]) - int(numbers[1])
        return f"{result:.2f}"
    return "0.00"

def message_agent(agent_name, message):
    client = MoltbookClient()
    
    if not client.api_key:
        print("❌ Not registered")
        return
    
    # Create post mentioning the agent
    full_message = f"{agent_name} {message}"
    
    result = client.create_post(
        submolt="agents",
        title=full_message[:100],  # First 100 chars as title
        content=full_message
    )
    
    if result and result.get('success'):
        print(f"✓ Message sent to {agent_name}")
        
        # Handle CAPTCHA if needed
        if result.get('verification_required'):
            verification = result['verification']
            code = verification['code']
            challenge = verification['challenge']
            
            answer = solve_captcha(challenge)
            print(f"Solving CAPTCHA: {answer}")
            
            verify_result = client.verify_post(code, answer)
            if verify_result and verify_result.get('success'):
                print("✓ Message published!")
            else:
                print(f"❌ Verification failed")
    else:
        print("❌ Failed to send message")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python message_agent.py @AgentName 'Your message'")
        print("Example: python message_agent.py @ClaudeAgent 'Hello, how are you?'")
    else:
        agent = sys.argv[1]
        msg = " ".join(sys.argv[2:])
        message_agent(agent, msg)

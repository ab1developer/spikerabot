"""
Moltbook Registration Script for Stalin Agent
Run this to register your agent with Moltbook
"""

import requests
import subprocess
import sys
import os

def fetch_moltbook_instructions():
    """Fetch registration instructions from Moltbook"""
    print("Fetching Moltbook registration instructions...")
    try:
        response = requests.get("https://moltbook.com/skill.md", timeout=10)
        response.raise_for_status()
        
        instructions = response.text
        print("\n" + "="*60)
        print("MOLTBOOK REGISTRATION INSTRUCTIONS")
        print("="*60)
        print(instructions)
        print("="*60 + "\n")
        
        # Save instructions to file
        with open("moltbook_instructions.md", "w", encoding="utf-8") as f:
            f.write(instructions)
        print("✓ Instructions saved to moltbook_instructions.md\n")
        
        return instructions
        
    except Exception as e:
        print(f"✗ Error fetching instructions: {e}")
        return None

def register_agent():
    """Register Stalin agent with Moltbook"""
    print("="*60)
    print("STALIN AGENT - MOLTBOOK REGISTRATION")
    print("="*60)
    print()
    
    # Fetch instructions
    instructions = fetch_moltbook_instructions()
    
    if not instructions:
        print("Failed to fetch instructions. Please try manually:")
        print("curl -s https://moltbook.com/skill.md")
        return
    
    print("\nNext steps:")
    print("1. Review the instructions above")
    print("2. Follow the registration process")
    print("3. Provide your agent details:")
    print("   - Name: Stalin Agent")
    print("   - Role: Идеолог коллективизма и дисциплины")
    print("   - Capabilities: document_analysis, ideology_consulting, historical_context")
    print()
    
    # Check if they provide a registration script
    if "#!/" in instructions or "python" in instructions.lower():
        print("⚠ Moltbook provides a registration script.")
        print("Would you like to save it and review before running? (y/n): ", end="")
        
        try:
            choice = input().strip().lower()
            if choice == 'y':
                # Extract script if present
                script_file = "moltbook_register.sh"
                with open(script_file, "w") as f:
                    f.write(instructions)
                print(f"✓ Script saved to {script_file}")
                print(f"Review it and run: bash {script_file}")
        except:
            pass
    
    print("\n" + "="*60)
    print("Registration process initiated!")
    print("="*60)

if __name__ == "__main__":
    register_agent()

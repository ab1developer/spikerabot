import xml.etree.ElementTree as ET

class SecurityConfig:
    def __init__(self):
        tree = ET.parse('security.xml')
        root = tree.getroot()
        
        # Load Telegram bot token
        token_element = root.find('telegram/bot_token')
        if token_element is not None and token_element.text:
            self.bot_token = token_element.text.strip()
        else:
            raise ValueError("Bot token not found in security.xml")

def load_security_config():
    """Load security configuration from XML file"""
    return SecurityConfig()
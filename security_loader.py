import xml.etree.ElementTree as ET

class SecurityConfig:
    def __init__(self):
        tree = ET.parse('security.xml')
        root = tree.getroot()
        
        # Load Telegram bot token
        self.bot_token = root.find('telegram/bot_token').text

def load_security_config():
    """Load security configuration from XML file"""
    return SecurityConfig()
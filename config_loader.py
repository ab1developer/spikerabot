import xml.etree.ElementTree as ET
from typing import List

def load_config():
    """Load configuration from XML file"""
    tree = ET.parse('config.xml')
    root = tree.getroot()
    
    # Load trigger words
    trigger_words = []
    for word in root.find('trigger_words').findall('word'):
        trigger_words.append(word.text)
    
    # Load system prompt content
    system_content = root.find('system_prompt/content').text
    
    # Load model temperature
    temperature = float(root.find('model_settings/temperature').text)
    
    # Load context history size
    context_size = int(root.find('model_settings/context_history_size').text)
    
    return trigger_words, system_content, temperature, context_size
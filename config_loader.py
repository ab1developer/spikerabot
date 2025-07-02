import xml.etree.ElementTree as ET
from typing import List

class Config:
    def __init__(self):
        tree = ET.parse('config.xml')
        root = tree.getroot()
        
        # Load trigger words
        self.trigger_words = []
        for word in root.find('trigger_words').findall('word'):
            self.trigger_words.append(word.text)
        
        # Load system prompt content
        self.system_content = root.find('system_prompt/content').text
        
        # Load model name
        self.model_name = root.find('model_settings/model_name').text
        
        # Load model temperature
        self.temperature = float(root.find('model_settings/temperature').text)
        
        # Load context history size
        self.context_size = int(root.find('model_settings/context_history_size').text)
        
        # Load logging settings
        self.log_directory = root.find('logging/directory').text
        self.max_file_size_mb = int(root.find('logging/max_file_size_mb').text)
        
        # Load summary triggers
        self.memory_summary_triggers = []
        for trigger in root.find('summary_triggers/memory').findall('trigger'):
            self.memory_summary_triggers.append(trigger.text)
        
        self.file_summary_triggers = []
        for trigger in root.find('summary_triggers/file').findall('trigger'):
            self.file_summary_triggers.append(trigger.text)

def load_config():
    """Load configuration from XML file"""
    return Config()
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
        
        # Load embedding model
        self.embedding_model = root.find('model_settings/embedding_model').text
        
        # Load documents path
        self.documents_path = root.find('model_settings/documents_path').text
        
        # Load request timeout
        self.request_timeout = float(root.find('model_settings/request_timeout').text)
        
        # Load debug log file
        self.debug_log_file = root.find('logging/debug_log_file').text
        
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
        
        # Load web search settings
        web_search = root.find('web_search')
        self.web_search_enabled = web_search.find('enabled').text.lower() == 'true'
        self.web_search_max_results = int(web_search.find('max_results').text)
        self.smart_search_enabled = web_search.find('smart_search_enabled').text.lower() == 'true' if web_search.find('smart_search_enabled') is not None else False
        self.smart_search_links = int(web_search.find('smart_search_links').text) if web_search.find('smart_search_links') is not None else 5
        self.parallel_extraction_workers = int(web_search.find('parallel_extraction_workers').text) if web_search.find('parallel_extraction_workers') is not None else 3
        self.semantic_ranking = web_search.find('semantic_ranking').text.lower() == 'true' if web_search.find('semantic_ranking') is not None else False
        
        # Load search sources
        self.search_sources = []
        sources = web_search.find('sources')
        if sources is not None:
            for source in sources.findall('source'):
                enabled = source.get('enabled', 'true').lower() == 'true'
                priority = int(source.get('priority', '99'))
                name = source.text.strip()
                if enabled:
                    self.search_sources.append({'name': name, 'priority': priority})
            self.search_sources.sort(key=lambda x: x['priority'])
        else:
            self.search_sources = [{'name': 'duckduckgo', 'priority': 1}]
        
        self.web_search_triggers = []
        for trigger in web_search.find('triggers').findall('trigger'):
            self.web_search_triggers.append(trigger.text)

def load_config():
    """Load configuration from XML file"""
    return Config()
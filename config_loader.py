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
        self.embedding_device = (
            root.findtext('model_settings/embedding_device') or 'cpu'
        ).strip() or 'cpu'
        
        # Load documents path
        self.documents_path = root.find('model_settings/documents_path').text
        
        # Load request timeout
        self.request_timeout = float(root.find('model_settings/request_timeout').text)
        self.ollama_context_window = int(
            root.findtext('model_settings/ollama_context_window') or '4096'
        )
        
        # Load hybrid retrieval setting
        hybrid_elem = root.find('model_settings/hybrid_retrieval')
        self.hybrid_retrieval = hybrid_elem.text.lower() == 'true' if hybrid_elem is not None else True

        self.kg_ingest_books = (
            root.findtext('knowledge_graph/ingest_books_on_startup') or 'true'
        ).strip().lower() == 'true'
        self.kg_checkpoint_chunks = max(1, int(
            root.findtext('knowledge_graph/checkpoint_chunks') or '25'
        ))
        self.kg_max_triplets_per_chunk = max(1, int(
            root.findtext('knowledge_graph/max_triplets_per_chunk') or '5'
        ))
        
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

        # Load intent router settings
        ir = root.find('intent_router')
        if ir is not None:
            self.intent_router_enabled = ir.find('enabled').text.lower() == 'true'
            self.intent_router_confidence_threshold = float(ir.find('confidence_threshold').text)
            self.intent_router_context_turns = int(ir.find('context_turns').text)
            self.intent_router_classifier_timeout = int(ir.find('classifier_timeout').text)
        else:
            self.intent_router_enabled = False
            self.intent_router_confidence_threshold = 0.70
            self.intent_router_context_turns = 2
            self.intent_router_classifier_timeout = 15

def load_config():
    """Load configuration from XML file"""
    return Config()

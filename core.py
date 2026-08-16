"""
StalinCore - Centralized Brain
Initializes all shared resources once and provides them to all services
"""

import model
from rag_embeddings import RAGEmbeddings
from knowledge_graph import KnowledgeGraphBuilder
from config_loader import load_config
from security_loader import load_security_config
from context_manager import ContextManager
from message_logger import MessageLogger
from web_search import web_searcher

class StalinCore:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        print("🧠 Initializing Stalin Core...")
        
        self.config = load_config()
        self.security_config = load_security_config()
        
        print("📚 Loading RAG embeddings...")
        self.rag = RAGEmbeddings()
        model.set_rag_embeddings(self.rag)
        
        print("🕸️ Loading Knowledge Graph...")
        self.kg = self.rag.kg_builder if hasattr(self.rag, 'kg_builder') else None
        
        self.context_manager = ContextManager()
        self.message_logger = MessageLogger()
        self.web_search = web_searcher
        
        self._initialized = True
        print("✅ Stalin Core ready!\n")
    
    def get_model_response(self, message, conversation_history, document_context=None):
        """Unified interface for LLM responses"""
        return model.modelResponse(message, conversation_history, document_context)

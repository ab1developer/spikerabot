from llama_index.core import KnowledgeGraphIndex, StorageContext, load_index_from_storage, Settings
from llama_index.core.graph_stores import SimpleGraphStore
from llama_index.core import Document
from llama_index.llms.ollama import Ollama
from config_loader import load_config
from debug_logger import debug_logger
import os
import json

# Disable NLTK downloads to prevent errors
try:
    import nltk
    nltk.data.path = []
    debug_logger.log_info("NLTK data path cleared to prevent downloads")
except ImportError:
    debug_logger.log_info("NLTK not found, skipping configuration")
    pass

class KnowledgeGraphBuilder:
    def __init__(self):
        try:
            # Configure local Ollama model for knowledge graph
            config = load_config()
            Settings.llm = Ollama(model=config.model_name, request_timeout=config.request_timeout)
            self.kg_index = None
            self._load_or_create_kg()
        except Exception as e:
            debug_logger.log_error(f"Knowledge graph initialization failed: {e}", e)
            self.kg_index = None
            print("Knowledge graph disabled due to initialization error")
    
    def _load_or_create_kg(self):
        """Load existing knowledge graph or create new one"""
        try:
            if os.path.exists("./storage") and os.path.exists("./storage/graph_store.json"):
                print("Loading existing knowledge graph...")
                storage_context = StorageContext.from_defaults(persist_dir="./storage")
                self.kg_index = load_index_from_storage(storage_context, index_id="knowledge_graph")
            else:
                raise FileNotFoundError("No existing knowledge graph found")
        except Exception as e:
            debug_logger.log_error(f"Failed to load knowledge graph: {e}", e)
            print("Creating new knowledge graph...")
            try:
                graph_store = SimpleGraphStore()
                storage_context = StorageContext.from_defaults(graph_store=graph_store)
                self.kg_index = KnowledgeGraphIndex([], storage_context=storage_context)
                self.kg_index.set_index_id("knowledge_graph")
                # Persist immediately after creation
                self.kg_index.storage_context.persist(persist_dir="./storage")
                debug_logger.log_info("New knowledge graph created and persisted successfully")
            except Exception as create_error:
                debug_logger.log_error(f"Failed to create knowledge graph: {create_error}", create_error)
                raise
    
    def add_document_to_kg(self, content: str, doc_name: str = "document"):
        """Add document content to knowledge graph"""
        if self.kg_index is None:
            return "Knowledge graph not available"
        try:
            document = Document(text=content, metadata={"source": doc_name})
            self.kg_index.insert(document)
            self.kg_index.storage_context.persist(persist_dir="./storage")
            return f"Added {doc_name} to knowledge graph"
        except Exception as e:
            debug_logger.log_error(f"Knowledge graph add error: {e}", e)
            print(f"Knowledge graph add error: {e}")
            return f"Document processed (knowledge graph unavailable)"
    
    def query_kg(self, query: str) -> str:
        """Query the knowledge graph"""
        if self.kg_index is None:
            return "Knowledge graph not available"
        try:
            query_engine = self.kg_index.as_query_engine()
            response = query_engine.query(query)
            return str(response)
        except Exception as e:
            debug_logger.log_error(f"Knowledge graph query error: {e}", e)
            print(f"Knowledge graph query error: {e}")
            return "Knowledge graph temporarily unavailable"
    
    def get_graph_summary(self) -> str:
        """Get summary of knowledge graph contents"""
        try:
            if hasattr(self.kg_index, 'graph_store') and hasattr(self.kg_index.graph_store, 'get_triplets'):
                triplets = self.kg_index.graph_store.get_triplets()
                return f"Knowledge graph contains {len(triplets)} relationships"
            return "Knowledge graph initialized"
        except:
            return "Knowledge graph status unknown"
    
    def build_kg_from_message_document(self, content: str, doc_name: str, message_text: str) -> str:
        """Build knowledge graph specifically for documents attached to messages"""
        try:
            # Add document to knowledge graph
            result = self.add_document_to_kg(content, doc_name)
            
            # Query based on message context
            if message_text and message_text.strip():
                kg_insights = self.query_kg(message_text)
                return f"{result}\n\nInsights: {kg_insights}"
            
            return result
        except Exception as e:
            return f"Error building knowledge graph: {str(e)}"
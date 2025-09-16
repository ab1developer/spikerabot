from llama_index.core import KnowledgeGraphIndex, StorageContext, load_index_from_storage, Settings
from llama_index.core.graph_stores import SimpleGraphStore
from llama_index.core import Document
from llama_index.llms.ollama import Ollama
from config_loader import load_config
import os
import json

class KnowledgeGraphBuilder:
    def __init__(self):
        # Configure local Ollama model for knowledge graph
        config = load_config()
        Settings.llm = Ollama(model=config.model_name, request_timeout=config.request_timeout)
        self.kg_index = None
        self._load_or_create_kg()
    
    def _load_or_create_kg(self):
        """Load existing knowledge graph or create new one"""
        try:
            if os.path.exists("./storage") and os.path.exists("./storage/graph_store.json"):
                print("Loading existing knowledge graph...")
                storage_context = StorageContext.from_defaults(persist_dir="./storage")
                self.kg_index = load_index_from_storage(storage_context, index_id="knowledge_graph")
            else:
                raise FileNotFoundError("No existing knowledge graph found")
        except:
            print("Creating new knowledge graph...")
            graph_store = SimpleGraphStore()
            storage_context = StorageContext.from_defaults(graph_store=graph_store)
            self.kg_index = KnowledgeGraphIndex([], storage_context=storage_context)
            self.kg_index.set_index_id("knowledge_graph")
    
    def add_document_to_kg(self, content: str, doc_name: str = "document"):
        """Add document content to knowledge graph"""
        try:
            document = Document(text=content, metadata={"source": doc_name})
            self.kg_index.insert(document)
            self.kg_index.storage_context.persist(persist_dir="./storage")
            return f"Added {doc_name} to knowledge graph"
        except Exception as e:
            return f"Error adding to knowledge graph: {str(e)}"
    
    def query_kg(self, query: str) -> str:
        """Query the knowledge graph"""
        try:
            query_engine = self.kg_index.as_query_engine()
            response = query_engine.query(query)
            return str(response)
        except Exception as e:
            return f"Knowledge graph query error: {str(e)}"
    
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
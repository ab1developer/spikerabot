from llama_index.core import KnowledgeGraphIndex, StorageContext, load_index_from_storage, Settings
from llama_index.core.graph_stores import SimpleGraphStore
from llama_index.core import Document
from llama_index.llms.ollama import Ollama
from config_loader import load_config
from debug_logger import debug_logger
import os
import json
import spacy


class KnowledgeGraphBuilder:
    def __init__(self):
        try:
            # Configure local Ollama model for knowledge graph
            config = load_config()
            Settings.llm = Ollama(model=config.model_name, request_timeout=config.request_timeout)
            self.kg_index = None
            self.nlp = self._load_spacy_model()
            self._load_or_create_kg()
        except Exception as e:
            debug_logger.log_error(f"Knowledge graph initialization failed: {e}", e)
            self.kg_index = None
            print("Knowledge graph disabled due to initialization error")
    
    def _load_spacy_model(self):
        """Load Russian spaCy model with fallback"""
        try:
            nlp = spacy.load("ru_core_news_sm")
            debug_logger.log_info("Loaded Russian spaCy model")
            return nlp
        except OSError:
            debug_logger.log_info("Downloading Russian spaCy model...")
            os.system("python -m spacy download ru_core_news_sm")
            try:
                return spacy.load("ru_core_news_sm")
            except Exception as e:
                debug_logger.log_error(f"Failed to load spaCy model after download: {e}", e)
                print("Warning: spaCy model unavailable, knowledge graph will use fallback mode")
                return None
    
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
    
    def _extract_entities(self, text: str):
        """Extract named entities using spaCy"""
        if self.nlp is None:
            return []
        doc = self.nlp(text[:10000])
        entities = [(ent.text.strip(), ent.label_) for ent in doc.ents if len(ent.text.strip()) > 1]
        return entities
    
    def _extract_relations_with_llm(self, entities: list, text_context: str):
        """Use LLM to infer semantic relationships between entities"""
        if len(entities) < 2:
            return []
        
        entity_list = ", ".join([f"{e[0]} ({e[1]})" for e in entities[:15]])
        prompt = f"""Из текста извлеките связи между сущностями в формате: субъект|отношение|объект

Сущности: {entity_list}

Текст: {text_context[:1500]}

Верните только связи, по одной на строку. Пример:
Сталин|родился_в|Гори
Гори|находится_в|Грузия"""
        
        try:
            response = Settings.llm.complete(prompt)
            triplets = []
            for line in str(response).strip().split('\n'):
                if '|' in line:
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) == 3 and all(parts):
                        triplets.append(tuple(parts))
            return triplets[:20]
        except Exception as e:
            debug_logger.log_error(f"LLM relation extraction error: {e}", e)
            return []
    
    def add_document_to_kg(self, content: str, doc_name: str = "document"):
        """Add document content to knowledge graph with semantic extraction"""
        if self.kg_index is None:
            return "Knowledge graph not available"
        try:
            # Extract entities with spaCy
            entities = self._extract_entities(content)
            debug_logger.log_info(f"Extracted {len(entities)} entities from {doc_name}")
            
            # Extract relationships with LLM
            triplets = self._extract_relations_with_llm(entities, content)
            debug_logger.log_info(f"Extracted {len(triplets)} relationships from {doc_name}")
            
            # Add triplets to graph store
            for subj, rel, obj in triplets:
                try:
                    self.kg_index.graph_store.upsert_triplet(subj, rel, obj)
                except AttributeError:
                    # Fallback for older LlamaIndex versions
                    self.kg_index.graph_store.add_triplet(subj, rel, obj)
            
            # Also add document for fallback querying
            document = Document(text=content, metadata={"source": doc_name})
            self.kg_index.insert(document)
            
            self.kg_index.storage_context.persist(persist_dir="./storage")
            return f"Added {doc_name} to knowledge graph ({len(triplets)} relationships)"
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
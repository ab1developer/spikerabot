from llama_index.core import KnowledgeGraphIndex, StorageContext, load_index_from_storage, Settings
from llama_index.core.graph_stores import SimpleGraphStore
from llama_index.core import Document
from llama_index.core.schema import MetadataMode
from llama_index.llms.ollama import Ollama
from config_loader import load_config
from debug_logger import debug_logger
from inference_scheduler import foreground_inference, inference_scheduler
import os
import json
import spacy
import hashlib
from pathlib import Path
import threading
import tempfile


class KnowledgeGraphBuilder:
    def __init__(self):
        self._graph_lock = threading.RLock()
        self.ingestion_thread = None
        self.ingestion_error = None
        try:
            # Configure local Ollama model for knowledge graph
            config = load_config()
            self.config = config
            Settings.llm = Ollama(
                model=config.model_name,
                request_timeout=config.request_timeout,
                context_window=config.ollama_context_window,
                thinking=False,
                additional_kwargs={'num_predict': 512},
            )
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
                self.kg_index = load_index_from_storage(
                    storage_context, index_id="knowledge_graph",
                    include_embeddings=True,
                    max_triplets_per_chunk=self.config.kg_max_triplets_per_chunk,
                )
            else:
                raise FileNotFoundError("No existing knowledge graph found")
        except Exception as e:
            debug_logger.log_error(f"Failed to load knowledge graph: {e}", e)
            print("Creating new knowledge graph...")
            try:
                graph_store = SimpleGraphStore()
                # Keep other indexes if only the graph needs to be recreated.
                if os.path.exists("./storage/index_store.json"):
                    storage_context = StorageContext.from_defaults(persist_dir="./storage")
                else:
                    storage_context = StorageContext.from_defaults(graph_store=graph_store)
                self.kg_index = KnowledgeGraphIndex(
                    [], storage_context=storage_context, include_embeddings=True,
                    max_triplets_per_chunk=self.config.kg_max_triplets_per_chunk,
                )
                self.kg_index.set_index_id("knowledge_graph")
                # Persist immediately after creation
                self._persist_graph_state()
                debug_logger.log_info("New knowledge graph created and persisted successfully")
            except Exception as create_error:
                debug_logger.log_error(f"Failed to create knowledge graph: {create_error}", create_error)
                raise

    def _load_book_progress(self):
        path = Path('storage/knowledge_graph_ingestion.json')
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('version') != 1 or data.get('model') != self.config.model_name:
            return {}
        return data.get('nodes', {})

    def _book_node_fingerprint(self, node):
        content = node.get_content(metadata_mode=MetadataMode.NONE)
        payload = content + json.dumps(node.metadata, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def _persist_graph_state(self):
        # Individual files must remain valid even if the daemon is interrupted
        # during a checkpoint. Persist a complete snapshot before replacing them.
        directory = Path('storage')
        directory.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.kg-checkpoint-', dir=directory) as staging:
            self.kg_index.storage_context.persist(persist_dir=staging)
            for path in Path(staging).iterdir():
                path.replace(directory / path.name)

    def _save_book_progress(self, progress):
        # Save the graph first: a crash before the checkpoint merely repeats
        # idempotent upserts, instead of skipping relationships that weren't saved.
        with self._graph_lock:
            self._persist_graph_state()
            path = Path('storage/knowledge_graph_ingestion.json')
            temporary = path.with_suffix('.json.tmp')
            temporary.write_text(json.dumps({
                'version': 1, 'model': self.config.model_name, 'nodes': progress,
            }), encoding='utf-8')
            temporary.replace(path)

    def ingest_book_nodes(self, nodes):
        """Backfill existing book passages; successful checkpoints survive restart."""
        if self.kg_index is None:
            raise RuntimeError('Knowledge graph is unavailable')
        progress = self._load_book_progress()
        pending = [
            (node, self._book_node_fingerprint(node)) for node in nodes
            if progress.get(node.node_id) != self._book_node_fingerprint(node)
        ]
        if not pending:
            print('Knowledge graph book ingestion: already up to date.', flush=True)
            return 0
        print(f'Knowledge graph: extracting relationships from {len(pending)} book passages.', flush=True)
        completed = 0
        dirty = False
        try:
            for node, fingerprint in pending:
                # Inference runs outside the graph lock; bot queries can read
                # the completed graph while another passage is being extracted.
                with inference_scheduler.slot(background=True):
                    triplets = self.kg_index._extract_triplets(
                        node.get_content(metadata_mode=MetadataMode.NONE)
                    )[:self.config.kg_max_triplets_per_chunk]
                texts = [str(triplet) for triplet in triplets]
                embeddings = Settings.embed_model.get_text_embedding_batch(texts) if texts else []
                with self._graph_lock:
                    for triplet, embedding in zip(triplets, embeddings):
                        self.kg_index.upsert_triplet_and_node(triplet, node)
                        self.kg_index.index_struct.add_to_embedding_dict(str(triplet), embedding)
                    self.kg_index.storage_context.index_store.add_index_struct(self.kg_index.index_struct)
                    progress[node.node_id] = fingerprint
                completed += 1
                dirty = True
                if completed == 1 or completed % self.config.kg_checkpoint_chunks == 0:
                    self._save_book_progress(progress)
                    dirty = False
                    print(f'Knowledge graph ingestion: {completed}/{len(pending)} passages saved.', flush=True)
        finally:
            if dirty:
                self._save_book_progress(progress)
        print(f'Knowledge graph ingestion complete: {completed} passages processed.', flush=True)
        return completed

    def start_book_ingestion(self, vector_index):
        """Start only after the vector index and graph share their storage."""
        if self.kg_index is None or not self.config.kg_ingest_books:
            return None
        if self.ingestion_thread is not None and self.ingestion_thread.is_alive():
            return self.ingestion_thread
        node_ids = list(dict.fromkeys(vector_index.index_struct.nodes_dict.values()))
        nodes = vector_index.docstore.get_nodes(node_ids)

        def run():
            try:
                self.ingest_book_nodes(nodes)
            except Exception as exc:
                self.ingestion_error = exc
                debug_logger.log_error(f'Book graph ingestion failed; will resume on restart: {exc}', exc)
                print(f'Knowledge graph ingestion stopped: {exc}. Progress saved; restart to retry.', flush=True)

        self.ingestion_error = None
        self.ingestion_thread = threading.Thread(target=run, name='book-knowledge-graph', daemon=True)
        self.ingestion_thread.start()
        return self.ingestion_thread
    
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
    
    @foreground_inference
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
            
            with self._graph_lock:
                for subj, rel, obj in triplets:
                    self.kg_index.graph_store.upsert_triplet(subj, rel, obj)
                document = Document(text=content, metadata={"source": doc_name})
                self.kg_index.insert(document)
                self._persist_graph_state()
            return f"Added {doc_name} to knowledge graph ({len(triplets)} relationships)"
        except Exception as e:
            debug_logger.log_error(f"Knowledge graph add error: {e}", e)
            print(f"Knowledge graph add error: {e}")
            return f"Document processed (knowledge graph unavailable)"
    
    @foreground_inference
    def query_kg(self, query: str) -> str:
        """Query the knowledge graph"""
        if self.kg_index is None:
            return "Knowledge graph not available"
        try:
            with self._graph_lock:
                if not self.kg_index.graph_store.to_dict()['graph_dict']:
                    return ''
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
            if self.kg_index is None:
                return 'Knowledge graph not available'
            with self._graph_lock:
                graph = self.kg_index.graph_store.to_dict()['graph_dict']
                count = sum(len(relations) for relations in graph.values())
            return f"Knowledge graph contains {count} relationships"
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

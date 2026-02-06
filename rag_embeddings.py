from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings, StorageContext, load_index_from_storage, Document
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from config_loader import load_config
from knowledge_graph import KnowledgeGraphBuilder
import os
import tempfile
import requests
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import warnings
warnings.filterwarnings("ignore", message=".*UNEXPECTED.*")

class RAGEmbeddings:
    def __init__(self):
        config = load_config()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            Settings.embed_model = HuggingFaceEmbedding(model_name=config.embedding_model)
        self.index = None
        self.kg_builder = KnowledgeGraphBuilder()
        self.hybrid_retrieval = config.hybrid_retrieval
        self._load_or_build_index()
    
    def _load_or_build_index(self):
        if os.path.exists("./storage"):
            print("Loading saved index...")
            storage_context = StorageContext.from_defaults(persist_dir="./storage")
            self.index = load_index_from_storage(storage_context)
            print("Index loaded!")
        else:
            config = load_config()
            documents = SimpleDirectoryReader(config.documents_path).load_data()
            print(f"Documents loaded: {len(documents)}")
            print("Building vector index...")
            self.index = VectorStoreIndex.from_documents(documents, show_progress=True)
            self.index.storage_context.persist(persist_dir="./storage")
            print("Index built and saved!")
    
    def _reciprocal_rank_fusion(self, vector_results: list, kg_results: list, k: int = 60) -> list:
        """Merge results using reciprocal rank fusion"""
        scores = {}
        
        # Score vector results
        for rank, node in enumerate(vector_results, 1):
            doc_id = node.node_id
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
        
        # Score KG results (extract text from KG response)
        for rank, kg_text in enumerate(kg_results, 1):
            # Use text hash as ID for KG results
            doc_id = f"kg_{hash(kg_text)}"
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
        
        # Sort by score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked
    
    def get_relevant_context(self, query: str, top_k: int = 3) -> str:
        """Get relevant context using hybrid retrieval (vector + graph)"""
        # Vector search
        retriever = self.index.as_retriever(similarity_top_k=top_k * 2)
        vector_nodes = retriever.retrieve(query)
        
        if not self.hybrid_retrieval:
            # Simple concatenation (old behavior)
            vector_context = "\n\n".join([node.text for node in vector_nodes[:top_k]])
            kg_context = self.kg_builder.query_kg(query)
            return f"Vector Context:\n{vector_context}\n\nKnowledge Graph:\n{kg_context}"
        
        # Hybrid retrieval with reciprocal rank fusion
        kg_response = self.kg_builder.query_kg(query)
        
        # Extract KG text chunks (split by sentences)
        kg_chunks = [s.strip() for s in kg_response.split('.') if len(s.strip()) > 20]
        
        # Merge using reciprocal rank fusion
        fused_results = self._reciprocal_rank_fusion(vector_nodes, kg_chunks)
        
        # Build context from top results
        context_parts = []
        seen_ids = set()
        
        for doc_id, score in fused_results[:top_k]:
            if doc_id.startswith('kg_'):
                # KG result
                kg_idx = abs(hash(doc_id)) % len(kg_chunks)
                if kg_idx not in seen_ids:
                    context_parts.append(f"[KG] {kg_chunks[kg_idx]}")
                    seen_ids.add(kg_idx)
            else:
                # Vector result
                for node in vector_nodes:
                    if node.node_id == doc_id and doc_id not in seen_ids:
                        context_parts.append(f"[Vector] {node.text[:500]}")
                        seen_ids.add(doc_id)
                        break
        
        return "\n\n".join(context_parts)
    
    def _extract_epub_text(self, file_path: str) -> str:
        """Extract text from EPUB file"""
        try:
            book = epub.read_epub(file_path)
            text_content = []
            
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    soup = BeautifulSoup(item.get_content(), 'html.parser')
                    text_content.append(soup.get_text())
            
            return '\n'.join(text_content)
        except Exception as e:
            print(f"EPUB extraction error: {e}")
            return ""
    
    def analyze_document(self, file_path: str, query: str) -> str:
        """Analyze a single document and return relevant context"""
        try:
            # Handle different file types
            if file_path.lower().endswith('.epub'):
                content = self._extract_epub_text(file_path)
            else:
                # Read as text file
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            
            if not content.strip():
                return "Документ пуст или не удалось извлечь текст"
            
            # Add to knowledge graph
            doc_name = os.path.basename(file_path)
            kg_result = self.kg_builder.add_document_to_kg(content, doc_name)
            print(f"Knowledge graph: {kg_result}")
            
            # Create document manually for vector search
            documents = [Document(text=content)]
            temp_index = VectorStoreIndex.from_documents(documents)
            retriever = temp_index.as_retriever(similarity_top_k=3)
            nodes = retriever.retrieve(query)
            
            # Get knowledge graph insights
            kg_response = self.kg_builder.query_kg(query)
            
            vector_context = "\n\n".join([node.text for node in nodes])
            
            # Return both vector search results and full document content for LLM analysis
            return f"Document Content:\n{content[:2000]}...\n\nVector Search:\n{vector_context}\n\nKnowledge Graph:\n{kg_response}"
        except Exception as e:
            print(f"Document analysis error: {e}")
            return f"Ошибка анализа документа: {str(e)}"
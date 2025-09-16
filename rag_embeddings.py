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

class RAGEmbeddings:
    def __init__(self):
        config = load_config()
        Settings.embed_model = HuggingFaceEmbedding(model_name=config.embedding_model)
        self.index = None
        self.kg_builder = KnowledgeGraphBuilder()
        self._load_or_build_index()
    
    def _load_or_build_index(self):
        if os.path.exists("./storage"):
            print("Загружаем сохраненный индекс...")
            storage_context = StorageContext.from_defaults(persist_dir="./storage")
            self.index = load_index_from_storage(storage_context)
            print("Индекс загружен!")
        else:
            config = load_config()
            documents = SimpleDirectoryReader(config.documents_path).load_data()
            print(f"Загружено документов: {len(documents)}")
            print("Строим векторный индекс...")
            self.index = VectorStoreIndex.from_documents(documents, show_progress=True)
            self.index.storage_context.persist(persist_dir="./storage")
            print("Индекс построен и сохранен!")
    
    def get_relevant_context(self, query: str, top_k: int = 3) -> str:
        retriever = self.index.as_retriever(similarity_top_k=top_k)
        nodes = retriever.retrieve(query)
        vector_context = "\n\n".join([node.text for node in nodes])
        
        # Add knowledge graph context
        kg_context = self.kg_builder.query_kg(query)
        
        return f"Vector Context:\n{vector_context}\n\nKnowledge Graph:\n{kg_context}"
    
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
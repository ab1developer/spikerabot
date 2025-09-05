from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings, StorageContext, load_index_from_storage
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from config_loader import load_config
import os

class RAGEmbeddings:
    def __init__(self):
        config = load_config()
        Settings.embed_model = HuggingFaceEmbedding(model_name=config.embedding_model)
        self.index = None
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
        context = "\n\n".join([node.text for node in nodes])
        return context
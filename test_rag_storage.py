"""Regression checks for graph-only and mixed RAG storage."""
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from llama_index.core import (
    Document, KnowledgeGraphIndex, Settings, SimpleDirectoryReader, StorageContext,
    VectorStoreIndex, load_index_from_storage,
)
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.llms import MockLLM
from rag_embeddings import RAGEmbeddings


class TestEPUBReader(unittest.TestCase):
    def test_directory_reader_loads_epub_text(self):
        from ebooklib import epub

        with tempfile.TemporaryDirectory() as directory:
            book = epub.EpubBook()
            book.set_identifier('reader-regression')
            book.set_title('Reader regression')
            book.set_language('ru')
            chapter = epub.EpubHtml(title='Chapter', file_name='chapter.xhtml', lang='ru')
            chapter.content = '<html><body><p>Москва — столица России.</p></body></html>'
            book.add_item(chapter)
            book.add_item(epub.EpubNcx())
            book.add_item(epub.EpubNav())
            book.toc = (chapter,)
            book.spine = ['nav', chapter]
            epub.write_epub(str(Path(directory) / 'sample.epub'), book)

            documents = SimpleDirectoryReader(directory, raise_on_error=True).load_data()
            self.assertEqual(len(documents), 1)
            self.assertIn('Москва — столица России.', documents[0].text)


class TestRAGStorage(unittest.TestCase):
    def setUp(self):
        original_dir = os.getcwd()
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.addCleanup(os.chdir, original_dir)
        os.chdir(self.workspace.name)
        Settings.embed_model = MockEmbedding(embed_dim=8)
        Settings.llm = MockLLM(max_tokens=16)
        Settings.tokenizer = lambda text: text.split()
        Path('documents').mkdir()
        Path('documents/sample.txt').write_text('Paris is the capital of France.')

    def make_rag(self, graph=None):
        rag = RAGEmbeddings.__new__(RAGEmbeddings)
        rag.kg_builder = SimpleNamespace(kg_index=graph)
        return rag

    def test_graph_only_storage_builds_vector_and_preserves_both_indexes(self):
        graph = KnowledgeGraphIndex([])
        graph.set_index_id('knowledge_graph')
        graph.graph_store.upsert_triplet('Paris', 'capital_of', 'France')
        graph.storage_context.persist(persist_dir='storage')
        rag = self.make_rag(graph)
        with patch('rag_embeddings.load_config', return_value=SimpleNamespace(
            documents_path='documents'
        )):
            rag._load_or_build_index()
        self.assertIsInstance(rag.index, VectorStoreIndex)
        self.assertTrue(rag.index.as_retriever().retrieve('France'))
        self.assertIs(rag.index.storage_context, graph.storage_context)

        # A later graph write must not erase the vector index from disk.
        graph.storage_context.persist(persist_dir='storage')
        storage = StorageContext.from_defaults(persist_dir='storage')
        self.assertEqual(
            {struct.index_id for struct in storage.index_store.index_structs()},
            {'knowledge_graph', 'vector_index'},
        )
        restored_graph = load_index_from_storage(storage, index_id='knowledge_graph')
        self.assertEqual(restored_graph.graph_store.get('Paris'), [['capital_of', 'France']])
        restored_rag = self.make_rag(restored_graph)
        with patch('rag_embeddings.SimpleDirectoryReader') as reader:
            restored_rag._load_or_build_index()
            reader.assert_not_called()
        self.assertIsInstance(restored_rag.index, VectorStoreIndex)
        self.assertTrue(restored_rag.index.as_retriever().retrieve('France'))

    def test_existing_vector_with_legacy_id_is_loaded_without_rebuild(self):
        vector = VectorStoreIndex.from_documents([Document(text='Existing document.')])
        vector.storage_context.persist(persist_dir='storage')
        rag = self.make_rag()
        with patch('rag_embeddings.SimpleDirectoryReader') as reader:
            rag._load_or_build_index()
            reader.assert_not_called()
        self.assertIsInstance(rag.index, VectorStoreIndex)
        self.assertEqual(rag.index.index_id, vector.index_id)
        self.assertTrue(rag.index.as_retriever().retrieve('document'))


if __name__ == '__main__':
    unittest.main()

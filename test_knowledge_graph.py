"""Exercise book backfill, restart recovery, and shared index persistence."""
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from llama_index.core import KnowledgeGraphIndex, Settings, StorageContext, VectorStoreIndex
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.llms import MockLLM
from llama_index.core.schema import TextNode
from knowledge_graph import KnowledgeGraphBuilder
from rag_embeddings import RAGEmbeddings


class TestBookGraphIngestion(unittest.TestCase):
    def setUp(self):
        original_dir = os.getcwd()
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.addCleanup(os.chdir, original_dir)
        os.chdir(workspace.name)
        Settings.embed_model = MockEmbedding(embed_dim=8)
        Settings.llm = MockLLM(max_tokens=16)
        Settings.tokenizer = lambda text: text.split()
        self.builder = KnowledgeGraphBuilder.__new__(KnowledgeGraphBuilder)
        self.builder._graph_lock = threading.RLock()
        self.builder.ingestion_thread = None
        self.builder.ingestion_error = None
        self.builder.config = SimpleNamespace(
            model_name='test-model', kg_ingest_books=True,
            kg_checkpoint_chunks=2, kg_max_triplets_per_chunk=5,
        )
        self.builder.kg_index = KnowledgeGraphIndex([], include_embeddings=True)
        self.builder.kg_index.set_index_id('knowledge_graph')
        self.nodes = [TextNode(id_=str(i), text=f'Fact {i}', metadata={'file_name': 'book.epub'}) for i in range(3)]
        self.vector = VectorStoreIndex(nodes=self.nodes, storage_context=self.builder.kg_index.storage_context)
        self.vector.set_index_id('vector_index')
        self.vector.storage_context.persist(persist_dir='storage')

    def extraction(self, text):
        return [(text, 'relates_to', 'Book')]

    def test_empty_graph_contributes_no_context_until_first_relationship(self):
        with patch.object(self.builder.kg_index, 'as_query_engine') as query:
            self.assertEqual(self.builder.query_kg('test'), '')
            query.assert_not_called()

    def test_disabled_backfill_does_not_start_worker(self):
        self.builder.config.kg_ingest_books = False
        self.assertIsNone(self.builder.start_book_ingestion(self.vector))
        self.assertIsNone(self.builder.ingestion_thread)

    def test_failed_snapshot_does_not_overwrite_indexes_or_mark_progress(self):
        before = Path('storage/index_store.json').read_bytes()

        def fail_snapshot(persist_dir):
            Path(persist_dir, 'index_store.json').write_text('incomplete')
            raise OSError('snapshot failed')

        with patch.object(self.builder.kg_index.storage_context, 'persist', side_effect=fail_snapshot):
            with self.assertRaisesRegex(OSError, 'snapshot failed'):
                self.builder._save_book_progress({'0': 'fingerprint'})
        self.assertEqual(Path('storage/index_store.json').read_bytes(), before)
        self.assertFalse(Path('storage/knowledge_graph_ingestion.json').exists())
        self.assertEqual(list(Path('storage').glob('.kg-checkpoint-*')), [])

    def test_backfill_links_sources_embeds_relations_and_preserves_vector_index(self):
        before = Path('storage/default__vector_store.json').read_bytes()
        with patch.object(self.builder.kg_index, '_extract_triplets', side_effect=self.extraction):
            self.assertEqual(self.builder.ingest_book_nodes(self.nodes), 3)
        store = StorageContext.from_defaults(persist_dir='storage')
        self.assertEqual({s.index_id for s in store.index_store.index_structs()}, {'knowledge_graph', 'vector_index'})
        self.assertEqual(Path('storage/default__vector_store.json').read_bytes(), before)
        graph = store.index_store.get_index_struct('knowledge_graph')
        self.assertEqual(len(graph.embedding_dict), 3)
        self.assertEqual(set(graph.table['Fact 0']), {'0'})
        self.assertIn('3 relationships', self.builder.get_graph_summary())
        progress = json.loads(Path('storage/knowledge_graph_ingestion.json').read_text())
        self.assertEqual(set(progress['nodes']), {'0', '1', '2'})

        with patch.object(self.builder.kg_index, '_extract_triplets') as extract:
            self.assertEqual(self.builder.ingest_book_nodes(self.nodes), 0)
            extract.assert_not_called()

    def test_failure_checkpoints_successes_and_retries_only_unfinished_nodes(self):
        with patch.object(self.builder.kg_index, '_extract_triplets', side_effect=[
            self.extraction('Fact 0'), RuntimeError('Ollama failed')
        ]):
            with self.assertRaisesRegex(RuntimeError, 'Ollama failed'):
                self.builder.ingest_book_nodes(self.nodes)
        progress = json.loads(Path('storage/knowledge_graph_ingestion.json').read_text())
        self.assertEqual(set(progress['nodes']), {'0'})

        # Resume from disk, as a fresh startup would.
        storage = StorageContext.from_defaults(persist_dir='storage')
        from llama_index.core import load_index_from_storage
        self.builder.kg_index = load_index_from_storage(storage, index_id='knowledge_graph', include_embeddings=True)
        with patch.object(self.builder.kg_index, '_extract_triplets', side_effect=self.extraction) as extract:
            self.assertEqual(self.builder.ingest_book_nodes(self.nodes), 2)
            self.assertEqual([c.args[0] for c in extract.call_args_list], ['Fact 1', 'Fact 2'])
        self.assertIn('3 relationships', self.builder.get_graph_summary())

    def test_background_worker_returns_immediately_and_is_not_started_twice(self):
        entered, release = threading.Event(), threading.Event()

        def work(nodes):
            self.assertEqual([n.node_id for n in nodes], ['0', '1', '2'])
            entered.set()
            release.wait(3)

        with patch.object(self.builder, 'ingest_book_nodes', side_effect=work) as ingest:
            worker = self.builder.start_book_ingestion(self.vector)
            try:
                self.assertTrue(entered.wait(2))
                self.assertTrue(worker.is_alive())
                self.assertIs(self.builder.start_book_ingestion(self.vector), worker)
            finally:
                release.set()
                worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertIsNone(self.builder.ingestion_error)
            self.assertEqual(ingest.call_count, 1)

    def test_startup_backfills_even_when_vector_index_already_exists(self):
        config = SimpleNamespace(embedding_model='test', embedding_device='cpu', hybrid_retrieval=True)
        with patch('rag_embeddings.load_config', return_value=config), \
             patch('rag_embeddings.HuggingFaceEmbedding', return_value=MockEmbedding(embed_dim=8)), \
             patch('rag_embeddings.KnowledgeGraphBuilder', return_value=self.builder), \
             patch.object(self.builder, 'start_book_ingestion') as start:
            rag = RAGEmbeddings()
        self.assertEqual(rag.index.index_id, 'vector_index')
        start.assert_called_once_with(rag.index)

    def test_graph_context_fusion_keeps_the_corresponding_passages(self):
        sentences = [
            'First relationship has a distinct source passage',
            'Second relationship has another source passage',
            'Third relationship comes from the final passage',
        ]
        rag = RAGEmbeddings.__new__(RAGEmbeddings)
        rag.hybrid_retrieval = True
        rag.index = SimpleNamespace(as_retriever=lambda **kwargs: SimpleNamespace(retrieve=lambda query: []))
        rag.kg_builder = SimpleNamespace(query_kg=lambda query: '. '.join(sentences))
        self.assertEqual(rag.get_relevant_context('test'), '\n\n'.join('[KG] ' + s for s in sentences))


if __name__ == '__main__':
    unittest.main()

import ollama
from config_loader import load_config
import json
import hashlib

class OllamaEmbeddings:
    def __init__(self):
        self.config = load_config()
        self.model = self.config.model_name
        
    def get_embedding(self, text: str):
        """Generate text-based 'embedding' using Ollama"""
        prompt = f"Summarize this text in exactly 10 keywords separated by commas: {text[:1000]}"
        response = ollama.chat(model=self.model, messages=[{'role': 'user', 'content': prompt}])
        keywords = response.message.content.strip().split(',')
        # Convert keywords to simple hash-based vector
        vector = []
        for i in range(384):  # Create 384-dim vector
            hash_input = f"{''.join(keywords)}{i}"
            hash_val = int(hashlib.md5(hash_input.encode()).hexdigest()[:8], 16)
            vector.append((hash_val % 1000) / 1000.0)
        return vector
    
    def similarity(self, vec1, vec2):
        """Calculate cosine similarity"""
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        return dot_product / (norm1 * norm2) if norm1 * norm2 > 0 else 0
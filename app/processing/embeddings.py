from typing import List
from sentence_transformers import SentenceTransformer
import numpy as np

class EmbeddingProvider:
    """Deterministic Semantic Encoding Layer utilizing multilingual Sentence Transformers"""
    
    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.model_name = model_name
        self.dimension = 384
        self.normalized = True
        
        # We load model safely on CPU bounds
        self.model = SentenceTransformer(model_name)
        
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
            
        # Natively encode and output normalized dense vectors
        embeddings = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return embeddings.tolist()
        
    def embed(self, text: str) -> List[float]:
        if not text:
            return [0.0] * self.dimension
        return self.embed_batch([text])[0]

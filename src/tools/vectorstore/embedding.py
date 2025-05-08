from ollama import embed
import numpy as np
from chromadb import EmbeddingFunction, Embeddings, Documents

# Define Embedding Model to use
EMBEDDING_MODEL = "nomic-embed-text"

# Define a custom embedding function
class OllamaEmbeddingFunction(EmbeddingFunction):
    def __call__(self, documents: Documents) -> Embeddings:
        embd = embed(model=EMBEDDING_MODEL, input=documents)
        embeddings = [np.array(embd["embeddings"][0], dtype=np.float32)]
        return embeddings

if __name__ == "__main__":
    # instance of custom embedding function
    ollama_embed = OllamaEmbeddingFunction()
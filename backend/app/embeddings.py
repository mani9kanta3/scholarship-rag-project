"""
Turning text into numbers.

The model is bge-small-en-v1.5. It gives 384 floats per piece of text
and runs on the CPU in a few milliseconds, which is plenty for a corpus
of about fifty schemes.

Two things worth knowing about it:

1. It was trained with a short instruction in front of the *question*
   but nothing in front of the documents. So embed_query() adds that
   line and embed_texts() does not. Getting this backwards quietly
   costs a few points of retrieval accuracy and nothing looks broken.

2. The vectors come back normalised to length 1. That means cosine
   similarity is just the dot product, and Chroma's cosine distance
   turns into "1 minus similarity", which is why scoring elsewhere in
   the project is a plain subtraction.
"""

from sentence_transformers import SentenceTransformer

from . import config

# bge asks for this exact sentence in front of a search query.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# Loaded the first time it is needed and then kept. Reading 130 MB off
# the disk on every request would be the slowest thing in the pipeline.
_model = None


def get_model():
    """Load the embedding model once."""
    global _model
    if _model is None:
        print(f"Loading embedding model {config.EMBEDDING_MODEL} ...")
        _model = SentenceTransformer(
            config.EMBEDDING_MODEL,
            cache_folder=str(config.MODEL_DIR),
        )
    return _model


def embed_texts(texts):
    """
    Embed a list of document chunks.

    Returns a list of plain Python lists, not numpy arrays, because
    these go straight into Postgres as JSON and into Chroma as lists.
    """
    if not texts:
        return []

    vectors = get_model().encode(
        texts,
        normalize_embeddings=True,
        batch_size=32,
        show_progress_bar=len(texts) > 50,
    )
    return [vector.tolist() for vector in vectors]


def embed_query(question):
    """Embed one search query, with the instruction bge expects."""
    vector = get_model().encode(
        QUERY_PREFIX + question,
        normalize_embeddings=True,
    )
    return vector.tolist()

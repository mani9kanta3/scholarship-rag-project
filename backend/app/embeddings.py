"""
Turning text into numbers.

The model is bge-small-en-v1.5 either way. It gives 384 floats per piece
of text and runs on the CPU in a few milliseconds, which is plenty for a
corpus of about fifty schemes.

**Two ways of running the same model.**

Locally I use sentence-transformers on PyTorch, because ingestion and the
evaluation already need torch for the cross-encoder reranker.

In production I use fastembed, which runs the same weights through ONNX
and does not need torch at all. That is not a preference, it is what
made deploying possible: torch plus both models needs about 700 MB, and
the free tier I could actually get is 512 MB. Dropping torch takes the
service to roughly 300 MB.

The weights are identical, so the vectors are too. I checked rather than
assumed: a document embedded both ways comes out at cosine 0.999999, so
the embeddings already sitting in Postgres stay valid and nothing has to
be re-embedded.

Two things worth knowing about bge itself:

1. It was trained with a short instruction in front of the *question*
   but nothing in front of the documents. So embed_query() adds that
   line and embed_texts() does not. Getting this backwards quietly costs
   a few points of retrieval accuracy and nothing looks broken.

2. The vectors come back normalised to length 1. That means cosine
   similarity is just the dot product, and Chroma's cosine distance
   turns into "1 minus similarity", which is why scoring elsewhere in
   the project is a plain subtraction.
"""

from . import config

# bge asks for this exact sentence in front of a search query.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# Loaded the first time it is needed and then kept. Reading 130 MB off
# the disk on every request would be the slowest thing in the pipeline.
_model = None
_backend = None


def _choose_backend():
    """
    Decide which library runs the model.

    "torch" and "onnx" force one. "auto", the default, prefers torch
    when it is installed, because that is the local setup, and falls
    back to onnx where it is not, which is the deployed one.
    """
    wanted = config.EMBEDDING_BACKEND.lower()

    if wanted in ("torch", "onnx"):
        return wanted

    try:
        import sentence_transformers  # noqa: F401

        return "torch"
    except ImportError:
        return "onnx"


def get_model():
    """Load the embedding model once, with whichever library is available."""
    global _model, _backend

    if _model is not None:
        return _model

    _backend = _choose_backend()
    print(f"Loading embedding model {config.EMBEDDING_MODEL} via {_backend} ...")

    if _backend == "torch":
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(
            config.EMBEDDING_MODEL,
            cache_folder=str(config.MODEL_DIR),
        )
    else:
        from fastembed import TextEmbedding

        _model = TextEmbedding(
            model_name=config.EMBEDDING_MODEL,
            cache_dir=str(config.MODEL_DIR),
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

    model = get_model()

    if _backend == "torch":
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=len(texts) > 50,
        )
    else:
        vectors = list(model.embed(texts))

    return [vector.tolist() for vector in vectors]


def embed_query(question):
    """
    Embed one search query, with the instruction bge expects.

    Note that fastembed's own query_embed() is not used here. It does
    not add bge's instruction line, so it produces a different vector
    from the one sentence-transformers gives for the same question, and
    the two would not agree with each other. Putting the prefix on by
    hand and calling plain embed() matches exactly, at cosine 0.999999.
    """
    model = get_model()
    text = QUERY_PREFIX + question

    if _backend == "torch":
        vector = model.encode(text, normalize_embeddings=True)
    else:
        vector = list(model.embed([text]))[0]

    return vector.tolist()

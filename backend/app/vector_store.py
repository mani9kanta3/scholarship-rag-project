"""
The vector store, kept behind two functions on purpose.

Everything else in the project calls upsert() and search() and never
touches Chroma directly. If I ever move to Pinecone, this is the only
file that changes, and the retrieval code does not know the difference.

The important design point is that **Chroma is not the source of truth**.
Postgres holds every embedding in document_chunk.embedding. Chroma is an
index built from that. So if the chroma folder is deleted, or the free
tier restarts and wipes its disk, load_from_postgres() rebuilds it in a
few seconds with no re-embedding and nothing is lost.
"""

import chromadb

from . import config, db

COLLECTION_NAME = "scheme_chunks"

_client = None


def get_collection():
    """
    Open the Chroma collection, creating it the first time.

    hnsw:space cosine matters. The default is squared L2 distance, and
    because our vectors are normalised, cosine is the measure that maps
    cleanly onto "how similar is this, from 0 to 1".
    """
    global _client
    if _client is None:
        config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))

    return _client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def upsert(chunks):
    """
    Put chunks into the index.

    Each chunk is a dict with id, scheme_id, chunk_text, section,
    source_page and embedding. Upsert rather than add, so running
    ingestion twice replaces rows instead of duplicating them.
    """
    if not chunks:
        return 0

    collection = get_collection()
    collection.upsert(
        ids=[str(chunk["id"]) for chunk in chunks],
        embeddings=[chunk["embedding"] for chunk in chunks],
        documents=[chunk["chunk_text"] for chunk in chunks],
        metadatas=[
            {
                "scheme_id": chunk["scheme_id"],
                "section": chunk["section"],
                # Chroma will not store None, so a missing page becomes 0.
                "source_page": chunk["source_page"] or 0,
            }
            for chunk in chunks
        ],
    )
    return len(chunks)


def search(query_embedding, limit, scheme_ids=None):
    """
    Find the closest chunks.

    scheme_ids is the list Postgres handed us. When it is given, Chroma
    never even looks at the other schemes. That is the whole hybrid
    idea: the hard rules are settled in SQL first, and semantic search
    only runs inside what survived.

    Returns dicts with a similarity from 0 to 1, highest first.
    """
    where = None
    if scheme_ids is not None:
        if not scheme_ids:
            # The filter matched nothing. Searching everything instead
            # would hand back schemes the student does not qualify for,
            # which is exactly the mistake this design exists to avoid.
            return []
        where = {"scheme_id": {"$in": list(scheme_ids)}}

    result = get_collection().query(
        query_embeddings=[query_embedding],
        n_results=limit,
        where=where,
    )

    hits = []
    # Chroma answers in lists of lists, one per query. We only sent one.
    for chunk_id, text, meta, distance in zip(
        result["ids"][0],
        result["documents"][0],
        result["metadatas"][0],
        result["distances"][0],
    ):
        hits.append(
            {
                "chunk_id": int(chunk_id),
                "scheme_id": meta["scheme_id"],
                "section": meta["section"],
                "source_page": meta["source_page"] or None,
                "chunk_text": text,
                # Cosine distance is 1 minus cosine similarity.
                "similarity": round(1 - distance, 4),
            }
        )
    return hits


def load_from_postgres():
    """
    Rebuild the whole index from Postgres.

    Called at API startup. It reads embeddings that already exist, so it
    costs no model time and no money, and it means a wiped Chroma folder
    is an inconvenience rather than a data loss.
    """
    rows = db.fetch_all(
        """
        SELECT id, scheme_id, chunk_text, section, source_page, embedding
        FROM document_chunk
        ORDER BY id
        """
    )
    count = upsert(rows)
    print(f"Chroma index built from Postgres: {count} chunks.")
    return count


def reset():
    """Throw the index away. Used by ingestion before a full rebuild."""
    global _client
    if _client is None:
        get_collection()
    try:
        _client.delete_collection(COLLECTION_NAME)
    except Exception:
        # Not there yet on a first run. Nothing to delete.
        pass


def count():
    """How many chunks are in the index right now."""
    return get_collection().count()

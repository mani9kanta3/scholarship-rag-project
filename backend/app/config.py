"""
Every setting the project needs, read once from the .env file.

I keep them all here instead of calling os.getenv() around the code.
If a key is missing I want one clear error when the app starts, not a
None turning up in the middle of a query an hour later.

The paths at the bottom matter more than they look. My C: drive is
full, so the Hugging Face models and the Chroma index are both pushed
onto the project drive instead of the default home folder.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# backend/app/config.py -> backend/app -> backend -> the project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / "backend" / ".env")


def get(name, default=None, required=False):
    """
    Read one value from the environment.

    required=True means the project cannot run without it, so stop now
    with a message that names the key, instead of failing later with
    something confusing like "NoneType has no attribute".
    """
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"{name} is missing. Copy .env.example to .env and fill it in.")
    return value


# Postgres. The source of truth for criteria, chunks and embeddings.
DB_NAME = get("DB_NAME", "scholarship_rag")
DB_USER = get("DB_USER", "postgres")
DB_PASSWORD = get("DB_PASSWORD", "")
DB_HOST = get("DB_HOST", "localhost")
DB_PORT = get("DB_PORT", "5432")

# Hosted Postgres refuses plain connections. Neon and Render both want
# SSL, my laptop does not care, so "prefer" is the default and hosted
# environments set this to "require".
DB_SSLMODE = get("DB_SSLMODE", "prefer")

# Which model provider to use: "groq" or "gemini".
#
# The guide picks Gemini and the code still supports it. I moved to Groq
# during development because the Gemini free tier turned out to be 20
# requests a day per model, and this project needs about 300 to run its
# own evaluation once. Both are behind the same two functions in llm.py,
# so this is one line in the .env, not a rewrite.
LLM_PROVIDER = get("LLM_PROVIDER", "groq").lower()

GEMINI_API_KEY = get("GEMINI_API_KEY", "")
GEMINI_MODEL = get("GEMINI_MODEL", "gemini-2.5-flash-lite")

GROQ_API_KEY = get("GROQ_API_KEY", "")
GROQ_MODEL = get("GROQ_MODEL", "openai/gpt-oss-120b")

# A different model does the grading.
#
# Two reasons, and the second one is the real one. The free tier counts
# tokens per day per model, so putting the judge somewhere else roughly
# doubles what a day's evaluation can cover. But a model grading its own
# answers is also a bad idea on its own terms: it recognises its own
# phrasing and its own reasoning and marks them generously. Judge and
# generator being different models is the cheap version of not marking
# your own homework.
GROQ_JUDGE_MODEL = get("GROQ_JUDGE_MODEL", "openai/gpt-oss-safeguard-20b")

# Local models. Both are inference only, nothing is trained here.
EMBEDDING_MODEL = get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
RERANKER_MODEL = get("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

# Which library runs the embedding model: "torch", "onnx" or "auto".
#
# Same weights either way. torch is the local setup because ingestion
# and the evaluation need it for the cross-encoder anyway. onnx is the
# deployed one, because torch plus both models needs about 700 MB and
# the free tier is 512 MB. "auto" picks torch when it is installed.
EMBEDDING_BACKEND = get("EMBEDDING_BACKEND", "auto")

# The cross-encoder needs torch, so it cannot run where torch is not
# installed. Turning it off is a real loss and worth being straight
# about, but the evaluation measured its effect twice and got opposite
# answers both times, so on this eval set it sits inside the noise.
# Switching off a component I could not prove helps, in order to ship at
# all, is the trade I would rather make than not deploy.
RERANKER_ENABLED = get("RERANKER_ENABLED", "true").lower() != "false"

# bge-small returns 384 numbers per chunk. If the embedding model is
# changed this has to change with it, and the whole corpus has to be
# embedded again, because old and new vectors cannot be compared.
EMBEDDING_DIM = 384

# Langfuse and Sentry are optional. Blank keys mean "turned off".
LANGFUSE_PUBLIC_KEY = get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = get("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST = get("LANGFUSE_HOST", "https://cloud.langfuse.com")
SENTRY_DSN = get("SENTRY_DSN", "")

CORS_ORIGINS = get("CORS_ORIGINS", "http://localhost:5173").split(",")

# Folders.
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"                 # the scheme documents as downloaded
REVIEW_DIR = DATA_DIR / "review"           # the hand check of the extractions
EXTRACT_DIR = DATA_DIR / "extractions"     # what the model returned, kept so it is asked once
# These two are overridable by environment variable, because in a
# container the repository layout above does not exist. The image copies
# only the backend folder, so BASE_DIR ends up as "/" and the defaults
# would point at paths outside the app that a non-root user cannot
# create. Docker sets both explicitly.
CHROMA_DIR = Path(get("CHROMA_DIR", str(BASE_DIR / "backend" / "chroma")))
MODEL_DIR = Path(get("MODEL_DIR", str(BASE_DIR / "models")))

# sentence-transformers reads this environment variable when it decides
# where to save a model. Setting it here, before that library is ever
# imported, keeps a 130 MB download off my full C: drive.
os.environ.setdefault("HF_HOME", str(MODEL_DIR))

# Retrieval numbers, kept in one place so the eval can change them.
CANDIDATE_CHUNKS = 20      # how many chunks similarity search returns
CONTEXT_CHUNKS = 5         # how many survive the reranker and reach the model
# Below this cosine similarity the best match is too weak to answer from.
#
# This was 0.30, which was a guess, and the guess was useless. The
# evaluation showed the actual scores from bge-small on this corpus run
# from 0.64 to 0.91, so a floor of 0.30 sat far below anything that ever
# happens and the rule could never fire once. An abstention rule that
# cannot trigger is not a safety net, it is a comment.
#
# 0.75 sits below the weakest answerable question in the eval set, which
# scored 0.794, and above five of the eight trap questions. Two honest
# caveats: it was chosen by looking at the eval set, so the abstention
# numbers it produces are optimistic and a held out set would be needed
# to quote them properly; and three traps still score above it, because
# they ask an unanswerable thing about a scheme that really is in the
# corpus. Retrieval score cannot catch those. That is what the grounding
# check is for.
MIN_SIMILARITY = 0.75
NEAR_MISS_LIMIT = 5        # how many "you just missed this one" schemes to show
STALE_AFTER_DAYS = 365     # older than this and a deadline may have passed

# Below this share of verified fields, the extraction for a scheme is
# too shaky to build an assertion on, so the answer abstains instead.
MIN_EXTRACTION_CONFIDENCE = 0.5

# Run the LLM judge on this share of live answers. It always runs on the
# eval set; in production it costs tokens on every request, so it
# samples. 0.0 turns it off, 1.0 runs it every time.
JUDGE_SAMPLE_RATE = 0.2

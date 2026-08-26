# The backend image. Runs on Hugging Face Spaces, and on Render or any
# other container host without changes.
#
# Four things in here are deliberate.
#
# 1. torch comes from the CPU index. The default wheel pulls the whole
#    CUDA runtime, about 2.5 GB, and there is no GPU on a free tier to
#    use it.
#
# 2. The embedding model and the reranker are downloaded during the
#    build. Otherwise the first person to arrive after a restart waits
#    for a 220 MB download before they get an answer.
#
# 3. It runs as a normal user, not root. Hugging Face Spaces expects
#    uid 1000, and the writable folders have to belong to that user or
#    the app cannot build its own index.
#
# 4. CHROMA_DIR and MODEL_DIR are set explicitly. The image copies only
#    the backend folder, so the repository layout config.py works out
#    from does not exist here and the defaults would point outside /app.

FROM python:3.12-slim

# Hugging Face Spaces runs containers as uid 1000.
RUN useradd -m -u 1000 user

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/app/models \
    MODEL_DIR=/app/models \
    CHROMA_DIR=/app/chroma \
    PORT=8000

WORKDIR /app

# psycopg2-binary ships its own libpq, so no build tools are needed.
COPY --chown=user requirements.txt .

RUN pip install --no-cache-dir torch==2.13.0 \
        --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .

# Pull both models into the image, into the folder the app will read.
RUN python -c "\
from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('BAAI/bge-small-en-v1.5', cache_folder='/app/models'); \
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2', cache_folder='/app/models')" \
 && mkdir -p /app/chroma \
 && chown -R user:user /app

USER user

EXPOSE 8000

# One worker. Each one loads both models into memory, and even 16 GB is
# no reason to hold two copies of them for a demo.
#
# The port comes from the environment so the same image works on hosts
# that hand you one, and falls back to 8000 where they do not.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]

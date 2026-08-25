# The backend, for Render.
#
# Two things in here are deliberate and worth reading.
#
# 1. torch comes from the CPU index. The default wheel pulls the whole
#    CUDA runtime, which is about 2.5 GB, and there is no GPU on the
#    free tier to use it. This keeps the image small enough to build.
#
# 2. The embedding model and the reranker are downloaded during the
#    build, not on the first request. Otherwise the first student to
#    arrive after a restart waits for a 130 MB download before they get
#    an answer, and on a free tier that restart happens often.

FROM python:3.12-slim

# Keep the models on a path we control, so the download at build time
# and the load at runtime agree about where they live.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/models

WORKDIR /app

# psycopg2-binary ships its own libpq, so no build tools are needed.
COPY requirements.txt .

RUN pip install --no-cache-dir torch==2.13.0 \
        --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

COPY . .

# Pull both models into the image.
RUN python -c "\
from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('BAAI/bge-small-en-v1.5', cache_folder='/models'); \
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2', cache_folder='/models')"

EXPOSE 8000

# One worker. Each one loads both models into memory, and the free tier
# does not have the RAM for two.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

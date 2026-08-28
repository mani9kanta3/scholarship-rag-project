"""
The entry point for the Hugging Face Space.

Hugging Face gives 16 GB of memory on the free Gradio runtime and
charges for the Docker one, so the API is served from inside a Gradio
Space instead of from a container. That matters more than it sounds:
this backend needs about 700 MB with PyTorch and both models loaded, and
every 512 MB free tier I looked at would have killed it on the first
request. Deploying somewhere with enough memory is what lets the
cross-encoder stay switched on, which in turn keeps the deployed system
the same as the one the evaluation measured.

How it fits together. The FastAPI app is the real application and keeps
every one of its routes. A small Gradio page is mounted on top of it at
the root, so a person who opens the Space sees something readable
instead of a 404, and anything under /api still reaches FastAPI.

The file is not called app.py on purpose. The package next to it is
already called app, and a module and a package with the same name in the
same folder is a fight you do not want to have. The Space README points
at this filename instead.
"""

import os

import gradio as gr
import uvicorn

from app import config, db, vector_store
from app.main import app as api

# Hugging Face expects the process to listen on 7860.
PORT = int(os.environ.get("PORT", 7860))

INTRO = """
# Scholarship Eligibility Assistant

The API behind a hybrid RAG system over 44 Indian scholarship schemes.

Eligibility rules are pulled out of the scheme documents into typed database
columns and compared in **SQL**, because comparing two numbers is arithmetic
and not similarity. Semantic search then runs **only inside the schemes that
survived that filter**. Nothing is stated in an answer unless the number behind
it can be traced back to a source.

### Endpoints

| Endpoint | What it does |
|---|---|
| `POST /api/eligibility` | Profile in, matching schemes with reasons and near misses out. No model involved. |
| `POST /api/ask` | A question. Answer with citations, or an honest refusal. |
| `GET /api/schemes` | Browse the corpus. |
| `GET /api/schemes/{id}` | One scheme, its rules, and the sentence each rule was read from. |
| `GET /api/eval/latest` | This system's own evaluation numbers, including the bad ones. |
| `GET /api/health` | Uptime ping and the live query log summary. |

**[Open the interactive API docs](/docs)**

Code, the evaluation, and an honest write up of what it gets wrong:
[github.com/mani9kanta3/scholarship-rag-project](https://github.com/mani9kanta3/scholarship-rag-project)
"""


def status():
    """
    A plain readout of what the service can see right now.

    No language model is called from this page on purpose. The Space is
    public, the API key is not, and an open text box wired to a paid
    model is an invitation. The demo lives on the frontend; this page is
    just here to prove the thing is up and connected.
    """
    try:
        schemes = db.fetch_one("SELECT count(*) AS n FROM scheme")["n"]
        chunks = db.fetch_one("SELECT count(*) AS n FROM document_chunk")["n"]
        indexed = vector_store.count()
    except Exception as error:
        return f"Cannot reach the database right now.\n\n`{str(error)[:300]}`"

    return (
        f"**Schemes:** {schemes}  \n"
        f"**Text chunks:** {chunks}  \n"
        f"**Chunks in the search index:** {indexed}  \n"
        f"**Answering model:** `{config.GROQ_MODEL}`  \n"
        f"**Embedding model:** `{config.EMBEDDING_MODEL}`"
    )


with gr.Blocks(title="Scholarship Eligibility Assistant") as demo:
    gr.Markdown(INTRO)
    gr.Markdown("### Live status")
    readout = gr.Markdown(value="Checking ...")
    refresh = gr.Button("Check again", variant="secondary")

    demo.load(status, outputs=readout)
    refresh.click(status, outputs=readout)


# Gradio goes on at the root. The /api routes were registered first, so
# they still win; this only catches what they do not handle.
space = gr.mount_gradio_app(api, demo, path="/")


if __name__ == "__main__":
    uvicorn.run(space, host="0.0.0.0", port=PORT)

"""
Splitting a scheme document into chunks.

The obvious thing is to run a text splitter over the whole document and
take whatever comes out. I am not doing that, and the reason matters.

These documents already have headings, and the eligibility section is
short. If a splitter cuts it in half, the income limit ends up in one
chunk and the category list in another, and a question about "SC student
with income 2 lakh" now needs two chunks to answer instead of one. So
the rule here is: **one chunk per section**, and the splitter only gets
involved when a section is genuinely too long to fit.

That also means the "section" label stored with each chunk is exact
rather than a guess, which is what lets the retriever prefer eligibility
chunks for eligibility questions.
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter

# Roughly 200 words. Most sections are well under this and stay whole.
MAX_CHUNK_CHARS = 1200
CHUNK_OVERLAP = 150

# LangChain's splitter is genuinely useful here. It tries paragraph
# breaks first, then line breaks, then sentences, so a long section
# gets cut at a sensible place instead of mid word.
splitter = RecursiveCharacterTextSplitter(
    chunk_size=MAX_CHUNK_CHARS,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " "],
)


def chunk_document(document):
    """
    Turn one loaded document into a list of chunks.

    Each chunk carries the scheme name at the top. Without it a chunk
    reads like "Applicants must have an annual family income of less
    than INR 2.5 lakhs" with no clue which scheme that belongs to, and
    the embedding of that sentence is nearly identical for a dozen
    different schemes.
    """
    chunks = []
    name = document["name"]

    for section, text in document["sections"].items():
        if not text.strip():
            continue

        pieces = splitter.split_text(text) if len(text) > MAX_CHUNK_CHARS else [text]

        for piece in pieces:
            chunks.append(
                {
                    "chunk_text": f"{name}\n{section.title()}\n{piece.strip()}",
                    "section": section,
                    # Markdown has no pages. Real pdfs would fill this in.
                    "source_page": None,
                }
            )

    return chunks


if __name__ == "__main__":
    from ingestion.load_documents import load_all

    documents = load_all()
    total = 0
    for document in documents:
        pieces = chunk_document(document)
        total += len(pieces)

    print(f"{len(documents)} documents -> {total} chunks")
    print(f"average {total / len(documents):.1f} chunks per scheme")

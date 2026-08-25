"""
Reading the scheme documents out of data/raw.

Every file looks the same:

    # Scheme name

    Source URL: https://...
    Provider: Ministry of ...
    Fetched on: 2026-08-25

    ## Description
    ...
    ## Eligibility
    ...

So this file turns each one into a dict with the header fields and a
dict of sections. Nothing clever, but everything downstream depends on
it, so it checks that the header fields are actually there and complains
by name if one is missing.

A note on LangChain. The guide says to use its loaders where they save
real work, and PyPDFLoader does, so pdf files in data/raw go through it.
Markdown is already plain text, so loading it through a library would
just be an import for no reason.
"""

from app import config

# The headings I write in the raw files, and the short section name that
# goes into the database with every chunk. Keeping the two apart means I
# can rename a heading later without touching the stored data.
SECTION_NAMES = {
    "Description": "description",
    "Eligibility": "eligibility",
    "Benefits": "benefits",
    "Documents Required": "documents",
    "How to Apply": "how to apply",
    "Deadline": "deadline",
}


def parse_markdown(text, filename):
    """
    Turn one raw markdown file into a dict.

    Returns name, source_url, provider, fetched_on and sections.
    """
    name = None
    source_url = None
    provider = None
    fetched_on = None

    sections = {}
    current_section = None
    current_lines = []

    for line in text.splitlines():
        stripped = line.strip()

        if stripped.startswith("# ") and name is None:
            name = stripped[2:].strip()
            continue

        if stripped.startswith("## "):
            # A new heading, so store whatever the last one collected.
            if current_section:
                sections[current_section] = "\n".join(current_lines).strip()
            heading = stripped[3:].strip()
            current_section = SECTION_NAMES.get(heading, heading.lower())
            current_lines = []
            continue

        if current_section is None:
            # Still in the header block above the first ## heading.
            if stripped.startswith("Source URL:"):
                source_url = stripped[len("Source URL:"):].strip()
            elif stripped.startswith("Provider:"):
                provider = stripped[len("Provider:"):].strip()
            elif stripped.startswith("Fetched on:"):
                fetched_on = stripped[len("Fetched on:"):].strip()
            continue

        current_lines.append(line)

    # The last section never hits another heading, so save it here.
    if current_section:
        sections[current_section] = "\n".join(current_lines).strip()

    missing = [
        field
        for field, value in [
            ("title", name),
            ("Source URL", source_url),
            ("Provider", provider),
            ("Fetched on", fetched_on),
        ]
        if not value
    ]
    if missing:
        raise ValueError(f"{filename} is missing: {', '.join(missing)}")

    return {
        "name": name,
        "source_url": source_url,
        "provider": provider,
        "fetched_on": fetched_on,
        "source_file": filename,
        "sections": sections,
    }


def parse_pdf(path):
    """
    Read a pdf with PyPDFLoader.

    A pdf has no headings I can trust, so the whole thing lands in one
    "description" section and the criteria extraction reads it as a
    single block. The page number is kept because citations need it.

    The import sits inside the function on purpose. My corpus is all
    markdown today, and importing LangChain at the top would print a
    deprecation warning on every single run for a code path nothing
    reaches.
    """
    from langchain_community.document_loaders import PyPDFLoader

    pages = PyPDFLoader(str(path)).load()
    full_text = "\n".join(page.page_content for page in pages)

    return {
        "name": path.stem.replace("-", " ").title(),
        "source_url": "",
        "provider": "Unknown",
        "fetched_on": "",
        "source_file": path.name,
        "sections": {"description": full_text},
    }


def load_all():
    """
    Read every document in data/raw, sorted by filename.

    Sorted so that scheme ids come out the same on every rebuild. The
    eval questions store scheme ids as ground truth, so ids jumping
    around between runs would quietly break the eval.
    """
    documents = []

    for path in sorted(config.RAW_DIR.iterdir()):
        if path.suffix == ".md":
            text = path.read_text(encoding="utf-8")
            documents.append(parse_markdown(text, path.name))
        elif path.suffix == ".pdf":
            documents.append(parse_pdf(path))

    return documents


if __name__ == "__main__":
    docs = load_all()
    print(f"Read {len(docs)} documents from {config.RAW_DIR}")
    for doc in docs[:3]:
        print(f"  {doc['name']}  ->  sections: {list(doc['sections'])}")

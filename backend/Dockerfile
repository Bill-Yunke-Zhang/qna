FROM python:3.12-slim

WORKDIR /app

# System deps for asyncmy (MySQL C extension) and cryptography (for python-jose);
# git shallow-clones course repos registered by URL (docs/design-rag.md §7.4)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# MiniLM's tokenizer counts chunk sizes (docs/design-rag.md §6.2). Downloaded
# at build time from the revision pinned in services/rag/profiles.py (keep the
# two in sync), and kept outside /app, which dev Compose bind-mounts over.
ARG MINILM_REVISION=1110a243fdf4706b3f48f1d95db1a4f5529b4d41
ARG MINILM_TOKENIZER_SHA256=be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037
RUN mkdir -p /opt/tokenizers/minilm \
    && python -c "import urllib.request; urllib.request.urlretrieve('https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/${MINILM_REVISION}/tokenizer.json', '/opt/tokenizers/minilm/tokenizer.json')" \
    && echo "${MINILM_TOKENIZER_SHA256}  /opt/tokenizers/minilm/tokenizer.json" | sha256sum -c -

COPY . .

EXPOSE 8000

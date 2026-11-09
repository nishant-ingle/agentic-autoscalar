FROM python:3.11-slim

WORKDIR /app

# Install libpq for PostgreSQL connectivity
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu

# Pre-download the default embedding model into the container image
# This ensures zero internet dependencies or cold-start lag during cluster Job execution
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY . /app/

ENV PYTHONPATH=/app
ENTRYPOINT ["python", "-m", "epic5.approach_syn_generator"]

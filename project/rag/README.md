# Epic 5: Operational Memory & RAG Pipeline (`pgvector`)

This module implements **Operational Memory** for the `agentic_autoscalar` system. It allows the agentic reasoner to consult past incident post-mortems, SRE runbooks, and domain scaling heuristics before executing scaling decisions.

---

## 1. What is Operational Memory and RAG?

### The Core Problem:
Native Kubernetes Horizontal Pod Autoscaler (HPA) is purely reactive:
1. Traffic spikes $\rightarrow$ CPU spikes.
2. HPA observes high CPU $\rightarrow$ HPA adds replicas.
3. If the CPU spike was caused by a deadlocked database or a memory leak, scaling out pods creates more DB connections, exacerbating the problem and crashing the cluster.

### The Solution (RAG Operational Memory):
**RAG (Retrieval-Augmented Generation)** acts as the **"SRE Memory"** of our autoscaler:
1. **Embedding**: Text runbooks and incident post-mortems are converted into numerical vector arrays (dense embeddings) using a sentence transformer model (`all-MiniLM-L6-v2`, 384 dimensions).
2. **Vector Database**: These vectors are stored in PostgreSQL using the `pgvector` extension with an **HNSW (Hierarchical Navigable Small World)** vector index.
3. **Similarity Search**: When anomalous telemetry is observed (e.g., *"CPU 95%, p99 latency 2000ms"*), the reasoner converts that metric symptom into a query vector and executes a cosine distance search (`<=>`).
4. **Context Injection**: The top matching runbooks (e.g. *"Flash Traffic Surge: scale immediately by 2.5x and hold for 5m"*) are retrieved and injected into the LLM prompt.

---

## 2. Directory & Code Structure

```
project/rag/ (symlinked to ./rag at project root)
├── Dockerfile                  # Container definition with pre-cached embeddings model
├── Makefile                    # Target shortcuts for setup, seeding, and testing
├── README.md                   # Complete architectural guide and instructions
├── approaches.txt              # Multi-approach implementation strategy roadmap
├── requirements.txt            # Python dependencies (psycopg2-binary, sentence-transformers, etc.)
├── pytest.ini                  # Pytest configuration
├── epic5/
│   ├── __init__.py             # Public module exports
│   ├── approach_syn_generator.py # Core generator script (Approach 1 - Synthetic)
│   ├── config.yaml             # Runtime configuration (mode: synthetic, DB credentials)
│   └── synthetic_epic5.yaml    # 5-10 production-grade synthetic SRE incident runbooks
├── tests/
│   └── epic5/
│       └── test_approach_syn_generator.py # 7 automated unit and integration tests
└── k8s/
    └── epic5-approach-syn-job.yaml # Kubernetes ConfigMap and Job manifest for cluster execution
```

---

## 3. How to Run & Verify Locally

### Prerequisites:
- Local PostgreSQL instance with `pgvector` extension installed.
- Default database configured: `agentic_autoscalar_db` (user: `agentic_autoscalar`, password: `agentic_autoscalar`).

### Step 1: Run the Synthetic Ingestion Pipeline
From the project root:
```bash
# Execute via python in your virtualenv:
PYTHONPATH=project/rag ./venv/bin/python -m epic5.approach_syn_generator
```
Output:
```
[*] Embedding 5 incidents using all-MiniLM-L6-v2...
[✓] Successfully inserted 5 documents into rag_documents table.
[✓] Pipeline complete. 5 records loaded.
```

### Step 2: Verify in PostgreSQL
```bash
psql -U agentic_autoscalar -d agentic_autoscalar_db -c "SELECT id, title, created_at FROM rag_documents;"
```

### Step 3: Run the Automated Pytest Suite
```bash
cd project/rag
../../venv/bin/pytest tests/epic5/test_approach_syn_generator.py -v
```
All 7 tests verify configuration parsing, schema validation, vector embeddings generation, database initialization, bulk insertion, and cosine similarity queries (`<=>`).

---

## 4. How to Run in a Kubernetes Cluster

### Step 1: Build and Load Docker Image
```bash
docker build -t agentic_autoscalar:dev -f project/rag/Dockerfile project/rag
# If using k3d:
k3d image import agentic_autoscalar:dev -c agentic-cluster
```

### Step 2: Apply the Kubernetes Job Manifest
```bash
kubectl apply -f project/rag/k8s/epic5-approach-syn-job.yaml
```

### Step 3: Verify Job Completion
```bash
kubectl get jobs -n workload-system
kubectl logs job/epic5-approach-syn-job -n workload-system
```
The Job mounts `config.yaml` and `synthetic_epic5.yaml` via ConfigMap, connects to the cluster `postgres` service, runs migrations, generates embeddings, and exits with code 0.

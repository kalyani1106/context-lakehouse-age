# PDF → Context Lakehouse → Apache AGE Knowledge Graph Pipeline

A modular end-to-end prototype that automates document ingestion from raw PDFs into a structured Lakehouse abstraction, extracts entity and relationship context with page-level provenance, deduplicates canonical entities, and populates an Apache AGE (PostgreSQL) graph database for openCypher querying and interactive visual exploration.

---

## 1. Architectural Pipeline

```text
                        ┌─────────────────────────┐
                        │     User uploads PDF    │
                        └────────────┬────────────┘
                                     │
                                     ▼
                        ┌─────────────────────────┐
                        │    Lakehouse Storage    │ ◄── Raw PDF tier + Metadata Catalog
                        │  (StorageService Layer) │
                        └────────────┬────────────┘
                                     │
                                     ▼
                        ┌─────────────────────────┐
                        │   PDF Text Extraction   │ ◄── Page-level text, character offsets
                        │      (pypdf Engine)     │     Stored in EXTRACTED_PAGES tier
                        └────────────┬────────────┘
                                     │
                                     ▼
                        ┌─────────────────────────┐
                        │    Passage Chunking     │ ◄── Sliding window token overlap
                        │  (DocumentChunker Layer)│     Stored in CHUNKS tier
                        └────────────┬────────────┘
                                     │
                                     ▼
                        ┌─────────────────────────┐
                        │   Context Generation    │ ◄── Entities, Relationships, Summaries
                        │  (LLM / Heuristic NLP)  │     Stored in CONTEXT tier (JSON/Parquet)
                        └────────────┬────────────┘
                                     │
                                     ▼
                        ┌─────────────────────────┐
                        │  Entity Deduplication   │ ◄── Canonical names, alias mapping,
                        │   & Normalization       │     edge consolidation & confidence
                        └────────────┬────────────┘
                                     │
                                     ▼
                        ┌─────────────────────────┐
                        │   Apache AGE / Postgres │ ◄── Vertices (Labels + Properties)
                        │     Knowledge Graph     │     Edges (Types + Provenance)
                        └────────────┬────────────┘
                                     │
                                     ▼
                        ┌─────────────────────────┐
                        │  FastAPI API & Streamlit│ ◄── REST Endpoints + Vis.js Visualizer
                        │  Interactive Visualizer │     with Document Provenance Traceback
                        └─────────────────────────┘
```

---

## 2. Lakehouse Architecture & Storage Tiers

> **Note on Lakehouse Abstraction**:
> The local development Lakehouse implementation separates concerns across explicit architectural tiers using Parquet, DuckDB, and JSON file tables managed by `StorageService`. In production, this clean abstraction can be replaced with Delta Lake, Apache Iceberg, or Cloud Object Stores (S3/GCS/BigLake) without modifying the downstream pipeline contracts.

### Lakehouse Directory Layout
```text
backend/lakehouse_storage/
├── raw/               # Original unmodified PDF binaries ({doc_id}.pdf)
├── metadata/          # Document lifecycle catalog ({doc_id}.json)
├── extracted_pages/   # Page-level text as Parquet & JSON ({doc_id}.parquet / .json)
├── chunks/            # Bounded passage spans with token offsets ({doc_id}.parquet / .json)
├── context/           # Structured entities, relationships & metadata ({doc_id}.json / _entities.parquet)
└── graph_sync/        # Sync logs and ingestion metrics into Apache AGE ({doc_id}.json)
```

---

## 3. Provenance & Traceability

Every extracted entity and relationship retains complete provenance back to the source:
- `document_id`: Unique identifier of the uploaded PDF
- `document_name`: Original filename (e.g. `A Report on Context Lakehouse.pdf`)
- `page_number`: 1-indexed page where the entity or evidence was found
- `chunk_id`: Exact passage chunk identifier
- `source_text`: Exact excerpt / quote from the PDF

When clicking any vertex or edge in the UI or querying the API (`/graph/provenance`), this provenance is immediately inspectable.

---

## 4. Setup & Prerequisites

### Prerequisites
- **Python**: 3.10+ (tested on Python 3.14)
- **Docker**: For running PostgreSQL + Apache AGE
- **PostgreSQL / Apache AGE**: Existing `age-postgres` container on port `5455` (or started via `docker-compose.yml`)

### 1. Start PostgreSQL + Apache AGE (Docker)
If not already running:
```bash
docker-compose up -d
```
Container parameters:
- Port: `5455` (host) -> `5432` (container)
- User: `postgres`
- Password: `postgres`
- Database: `postgres`

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Default `.env` configuration:
```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5455
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
AGE_GRAPH_NAME=knowledge_graph
LAKEHOUSE_ROOT=./backend/lakehouse_storage

# LLM Extractor (Optional: uses High-Precision Heuristic NLP extractor if unset)
LLM_PROVIDER=auto
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

---

## 5. Ingestion Deduplication & Extraction Quality

1. **SHA-256 Content Hashing**:
   - Every uploaded PDF is hashed using SHA-256 upon upload.
   - If an identical PDF is uploaded (regardless of filename), the existing document ID and Lakehouse metadata are re-used without duplicating raw storage or creating duplicate catalog entries.
2. **Idempotent Graph Ingestion**:
   - Documents with status `COMPLETED` will not create duplicate vertices or edges in Apache AGE upon repeated runs unless `reprocess=True` is explicitly requested.
3. **High-Precision Semantic Extraction**:
   - Eliminates noise and entity explosion on small documents and resumes (e.g. 1-page resume produces ~19 meaningful entities and 8 clean relationships instead of 60+ noisy entities).
   - Strict stopword filtering and predicate-based relationship extraction (`EXTENDS`, `USES`, `WORKS_AT`, `STUDIED_AT`, `COMBINES`, `PROVIDES`, `CREATES`, `PART_OF`, `DEPENDS_ON`, `INTEGRATES_WITH`).
4. **Extraction Quality Statistics**:
   - For every processed document, the catalog and UI display total pages, passage chunks, canonical entities, directed relationships, extraction engine (`LLM` or `HEURISTIC_NLP`), processing time, and graph vertices/edges added.

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## 5. Running the Application

### Option A: Run the FastAPI REST API
```bash
py -3.14 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive Swagger API documentation is available at:
`http://localhost:8000/docs`

### Option B: Run the Streamlit Interactive Dashboard
```bash
streamlit run frontend/app.py
```
The web dashboard opens at `http://localhost:8501`.

---

## 6. Project Directory Layout

```text
context-lakehouse/
│
├── backend/
│   ├── __init__.py
│   ├── main.py                  # FastAPI Application Entrypoint
│   ├── config.py                # Environment and configuration settings
│   ├── pipeline.py              # PDF -> Lakehouse -> Apache AGE Orchestrator
│   ├── api/                     # REST API routes (PDF + Git Graphify)
│   ├── graph/                   # Apache AGE client & graph service
│   ├── context/                 # Semantic context & entity normalizer
│   ├── extraction/              # PDF text extractor & document chunker
│   ├── storage/                 # Lakehouse storage tiers & metadata catalog
│   └── git_graph/               # Git Repository Knowledge Graph ("Graphify") subsystem
│       ├── config.py
│       ├── pipeline.py          # Git Clone -> Scan -> AST/Config -> AGE Ingestion
│       ├── repository/          # Git clone, scanner, models
│       ├── parsing/             # AST, JS/TS, Config, Markdown parsers
│       ├── context/             # Entity extractor & normalizer
│       └── graph/               # Git graph service & sample Cypher queries
│
├── frontend/
│   ├── __init__.py
│   ├── app.py                   # Streamlit Multi-Modal Dashboard
│   ├── graph_visualizer.py      # Vis.js interactive graph visualizer & provenance inspector
│   └── static/                  # Offline vis-network static assets
│
├── tests/                       # Complete automated test suite (42 tests)
├── scripts/                     # Utility and demonstration scripts
├── requirements.txt
└── README.md
```

## 6. REST API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/documents/upload` | Upload PDF file to Lakehouse raw tier |
| `GET` | `/documents` | List all documents with processing status |
| `GET` | `/documents/{id}` | Get metadata and status for document |
| `POST` | `/documents/{id}/process` | Run end-to-end extraction and AGE ingestion |
| `GET` | `/documents/{id}/pages` | Retrieve page-level text extraction from Lakehouse |
| `GET` | `/documents/{id}/chunks` | Retrieve passage chunks from Lakehouse |
| `GET` | `/documents/{id}/context` | **Inspect structured context JSON before/alongside graph** |
| `GET` | `/documents/{id}/graph` | Retrieve document subgraph from Apache AGE |
| `DELETE` | `/documents/{id}` | Delete document and artifacts across all tiers |
| `GET` | `/graph/entities` | Query graph entities from Apache AGE with filters |
| `GET` | `/graph/relationships` | Query relationships from Apache AGE |
| `GET` | `/graph/full` | Get full knowledge graph for visual rendering |
| `POST` | `/graph/query` | **Execute raw Cypher queries against Apache AGE** |
| `GET` | `/graph/provenance` | **Retrieve complete source text and page provenance** |
| `GET` | `/graph/stats` | Total vertex and edge counts from Apache AGE |
| `GET` | `/health` | System and Apache AGE connectivity health check |

---

## 7. Sample Cypher Queries in Apache AGE

The system stores entities as vertices with labeled categories (`Technology`, `Concept`, `Organization`, `Person`, `Layer`) and relationships as directed typed edges (`EXTENDS`, `USES`, `PART_OF`, `DEPENDS_ON`, `IMPLEMENTS`, `INTEGRATES_WITH`, `CONTAINS`).

### 1. Find all entities
```cypher
MATCH (n)
RETURN n LIMIT 25;
```

### 2. Find all relationships with endpoints
```cypher
MATCH (a)-[r]->(b)
RETURN a, r, b LIMIT 25;
```

### 3. Find entities connected to "Apache AGE"
```cypher
MATCH (a {canonical_name: 'Apache AGE'})-[r]-(b)
RETURN a, r, b;
```

### 4. Find all Technology entities
```cypher
MATCH (n:Technology)
RETURN n;
```

### 5. Find EXTENDS relationships
```cypher
MATCH (a)-[r:EXTENDS]->(b)
RETURN a, r, b;
```

---

## 8. Running the Automated Test Suite

Run the full automated test suite (19 unit & integration tests) covering storage, extraction, context, deduplication, AGE graph ingestion, Cypher execution, API endpoints, and end-to-end real PDF processing:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

---

## 9. Example End-to-End Walkthrough

1. **Upload**: User uploads `A Report on Context Lakehouse.pdf`.
2. **Lakehouse Storage**: Stored in `backend/lakehouse_storage/raw/doc_xyz.pdf`, registered in `metadata/`.
3. **Extraction**: `PDFExtractor` reads 12 pages (1,418 words) into `extracted_pages/`.
4. **Chunking**: `DocumentChunker` splits text into 22 passage chunks in `chunks/`.
5. **Context Generation**: `ContextExtractor` extracts 141 canonical entities (e.g. `Context Lakehouse`, `PostgreSQL`, `Apache AGE`, `Semantic Layer`, `DuckDB`) and 73 relationships (e.g. `Product -[:USES]-> Telemetry`, `Apache AGE -[:EXTENDS]-> PostgreSQL`).
6. **Graph Ingestion**: `GraphService` creates vertices and edges in PostgreSQL Apache AGE with exact page numbers and evidence quotes.
7. **Exploration**: User queries Cypher or navigates the Vis.js interactive knowledge graph with click-to-view provenance.

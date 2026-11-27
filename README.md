# Meeting Intelligence Agent

A FastAPI application that indexes meeting transcripts and answers questions with
retrieved evidence. It helps users find decisions, owners, deadlines, risks, and
other details without rereading long transcripts.

## Features

- Upload `.txt`, `.md`, `.pdf`, `.docx`, and `.vtt` transcripts, up to 10 MB.
- Extract transcript text and split it into 500-token chunks with 75-token overlap.
- Create 736-dimensional embeddings through the configured embedding provider.
- Store and search vectors in ChromaDB using cosine similarity.
- Retrieve the top four relevant chunks and answer with source citations such as `[S1]`.
- Return compact source metadata by default; return full chunk evidence when explicitly
  requested (for example, “show evidence”).
- Handle common greetings and thanks with an LLM response without transcript retrieval.
- Provide meeting CRUD, indexing status, a browser chat, and API documentation.
- Use synchronous local indexing by default, with the Celery/Redis path retained as an
  optional mode.

Main endpoints:

- `GET /api/v1/health`
- Meeting CRUD under `/api/v1/meetings`; upload at `POST /api/v1/meetings/upload`
- Reindex at `POST /api/v1/meetings/{meeting_id}/index`; status at
  `GET /api/v1/meetings/{meeting_id}/index-status`
- `POST /api/v1/chat` and `POST /api/v1/ask`

## Architecture

```text
Transcript
    → Loader
    → Chunking
    → Embeddings
    → ChromaDB
    → Retriever
    → LLM
    → Answer with citations
```

For a normal question, the application embeds the question, retrieves relevant chunks,
and sends those chunks—not the entire transcript—to the LLM. The LLM is instructed to
answer only from that context and cite its sources. Retrieval uses the top four chunks;
there is no fixed similarity cutoff.

## Technology Stack

- Python
- FastAPI and Uvicorn
- Pydantic and `pydantic-settings`
- LangChain and LangChain Core
- ChromaDB and LangChain Chroma
- Custom REST clients for the embedding and chat providers
- SQLAlchemy and pyodbc for the optional SQL Server repository
- Celery and Redis for optional background indexing
- `python-dotenv` for local environment configuration

## Project Structure

```text
app/
├── api/
│   ├── dependencies.py           # Shared FastAPI dependencies, including repository access
│   ├── router.py                 # Combines health, meeting, chat, and ask routers
│   └── routes/
│       ├── ask.py                # Simple question/answer API
│       ├── chat.py               # Chat API with optional history
│       ├── health.py             # Health endpoint
│       └── meetings.py           # CRUD, upload, reindex, and indexing-status endpoints
├── rag/
│   ├── answering.py              # Retrieval, prompt construction, citations, and abstention
│   ├── components.py             # Custom model clients, Chroma client, and vector store
│   └── indexing.py               # Chunking and writing transcript documents to Chroma
├── repositories/
│   ├── protocols.py              # Meeting repository interface
│   ├── meeting_repository.py     # In-memory repository
│   └── sqlserver_meeting_repository.py # SQL Server repository
├── schemas/
│   ├── ask.py                    # Ask API request and response models
│   ├── chat.py                   # Chat, history, and source models
│   └── meeting.py                # Meeting CRUD and indexing-status models
├── services/
│   ├── indexing.py               # Local/Celery indexing dispatch and vector cleanup
│   └── transcripts.py            # Upload validation and TXT/MD/PDF/DOCX/VTT extraction
├── static/
│   └── index.html                # Browser chat and transcript-upload interface
├── workers/
│   ├── celery_app.py             # Celery configuration
│   └── tasks.py                  # Background indexing and vector-cleanup tasks
├── config.py                     # Validated application and provider settings
├── exceptions.py                 # Application exceptions
└── main.py                       # FastAPI app, repository setup, and static chat routes
sql/
└── 001_meetings.sql              # SQL Server table, index, and stored procedures
tests/
├── test_chat_provider.py         # Custom chat-provider and LCEL tests
├── test_embedding_provider.py    # Custom embedding-provider tests
├── test_local_indexing.py        # Local and optional Celery indexing tests
├── test_rag_small_talk.py        # Small-talk routing tests
└── test_rag_sources.py           # Source metadata and evidence-response tests
.env.example                      # Safe configuration template
compose.yaml                      # Optional Redis and Chroma services
requirements.txt                  # Python dependencies
```

The meeting routes validate and persist meeting records through the repository. The
indexing service selects local or Celery execution, then `rag/indexing.py` chunks and
stores documents. At question time, `rag/answering.py` retrieves and validates sources
before calling the configured LLM. API schemas and the static chat UI control how answers
and citations are returned and displayed.

## Indexing Flow

1. A transcript is uploaded through the chat page or `/api/v1/meetings/upload`.
2. The loader extracts text and rejects unsupported, empty, or oversized files.
3. `RecursiveCharacterTextSplitter` creates 500-token chunks with a 75-token overlap,
   using `cl100k_base`.
4. The embedding client sends each chunk to the configured endpoint and validates the
   returned 736-value vector.
5. Chunks, vectors, and meeting metadata are stored in the `meeting_transcripts` Chroma
   collection.

The built-in indexer records meeting title, date, chunk index, and indexing task ID.
Speaker and timestamp are shown in citations only if those fields are present in document
metadata; the indexer does not currently extract them from transcript text.

## Query Flow

1. The user submits a question to `/api/v1/chat` or `/api/v1/ask`.
2. Common small-talk matches go directly to the LLM with a suggested reply.
3. Other questions are embedded and used to retrieve the top four transcript chunks.
4. Stale or unindexed documents are excluded; the remaining excerpts are added to the
   prompt as sources `[S1]`, `[S2]`, and so on.
5. The LLM generates a grounded answer with citations.
6. The response displays compact source metadata. Full chunk text is included only when
   the question explicitly requests evidence, such as “show supporting text”.

## Environment Variables

Copy `.env.example` to `.env` if you do not already have a local configuration. `.env`
is ignored by Git; do not commit provider keys or connection strings.

| Variable | Purpose | Default |
|---|---|---|
| `APP_NAME` | FastAPI application name | `Meeting Intelligence Agent` |
| `APP_VERSION` | Application version | `0.1.0` |
| `API_V1_PREFIX` | Prefix for API routes | `/api/v1` |
| `DATABASE_BACKEND` | `memory` or `sqlserver` meeting repository | `memory` |
| `SQLSERVER_CONNECTION_STRING` | SQL Server connection; required for `sqlserver` | — |
| `INDEXING_MODE` | `local` or `celery` indexing | `local` |
| `LLM_API_KEY` | Chat provider key, sent as `X-API-KEY` | — |
| `LLM_BASE_URL` | Complete chat endpoint URL; sent unchanged | — |
| `LLM_MODEL` | Chat model identifier | `gpt-5-2-chat` |
| `LLM_TEMPERATURE` | Chat generation temperature | `0.0` |
| `LLM_TOP_P` | Chat sampling parameter | `0.9` |
| `LLM_MAX_TOKENS` | Maximum generated tokens | `1000` |
| `EMBEDDING_API_KEY` | Embedding provider key, sent as `X-API-KEY` | — |
| `EMBEDDING_API_URL` | Complete embeddings endpoint URL | — |
| `EMBEDDING_BASE_URL` | Legacy alternative; `/embeddings` is appended unless already present | — |
| `EMBEDDING_DIMENSIONS` | Expected and requested vector dimensions | `736` |
| `REDIS_URL` | Celery broker and result backend in `celery` mode | `redis://localhost:6379/0` |
| `CHROMA_HOST` | ChromaDB host | `localhost` |
| `CHROMA_PORT` | ChromaDB host port | `8001` |

The chat provider request uses the complete `LLM_BASE_URL` and sends `model`, `messages`,
`temperature`, `top_p`, and `max_tokens`. The embedding request sends `texts` and
`dimensions`; no embedding model field is sent by the current adapter. Configure both
endpoints and keys according to your provider's documentation.

## Run Locally

The default `INDEXING_MODE=local` indexes synchronously in the FastAPI process. Redis and
a Celery worker are not needed, but the ChromaDB service and model-provider endpoints must
be reachable.

### 1. Create a virtual environment and install dependencies

PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create `.env` from `.env.example` only if you do not already have one, then configure the
LLM, embedding provider, and Chroma settings.

### 2. Start ChromaDB

In a separate terminal:

```powershell
.\.venv\Scripts\chroma.exe run --host 127.0.0.1 --port 8001 --path "$env:LOCALAPPDATA\MeetingIntelligenceAgent\chroma"
```

### 3. Start FastAPI

```powershell
python -m uvicorn app.main:app --reload
```

Open the chat at <http://127.0.0.1:8000/chat>, API docs at
<http://127.0.0.1:8000/docs>, or health status at
<http://127.0.0.1:8000/api/v1/health>.

Local create, update, upload, and reindex requests wait for embedding and storage to finish.
Use `DATABASE_BACKEND=memory` for a simple local setup; in-memory meeting records are lost
when the FastAPI process stops.

### Optional: Celery and Redis

To enable background indexing, set `INDEXING_MODE=celery`, then start Redis and ChromaDB
(for example, with `docker compose up -d`). Start the worker in another terminal:

```powershell
python -m celery -A app.workers.celery_app:celery_app worker --pool=solo --loglevel=info
```

Start FastAPI as above. The Celery mode uses `REDIS_URL` for job queuing and status.

### Optional: SQL Server

Run [`sql/001_meetings.sql`](./sql/001_meetings.sql) against the target database, set
`DATABASE_BACKEND=sqlserver`, and configure `SQLSERVER_CONNECTION_STRING`. The SQL Server
repository uses the stored procedures in that script.

Run the test suite with:

```powershell
python -m unittest discover -s tests -v
```

## Design Decisions

- **ChromaDB:** provides persistent vector storage and cosine-similarity search locally or
  as a service.
- **Embeddings:** represent text by semantic meaning, so a query can find relevant passages
  even when it uses different words from the transcript.
- **500-token chunks with 75-token overlap:** keep passages small enough for retrieval and
  model context while retaining a little context across chunk boundaries.
- **Retrieval before generation:** supplies a small set of transcript evidence to the LLM
  instead of sending the entire transcript, improving relevance and making citations
  traceable.

## Current Limitations

- Local synchronous indexing is the default and can make upload or update requests take
  time for long transcripts. The current embedding adapter sends one text per provider
  request. Celery/Redis support is implemented but disabled by default.
- Blob Storage and shared-drive ingestion are not implemented.
- Speaker and timestamp metadata are not currently extracted by the built-in indexer.
- PDF OCR is not supported; PDFs need extractable text.
- Chat history is sent by the browser for the current conversation but is not persisted.
- Grounding instructions and low temperature reduce unsupported answers but cannot guarantee
  that an LLM will never hallucinate.

## Future Enhancements

- Enable Redis and Celery background indexing for production workloads.
- Add Blob Storage and shared-drive integrations.
- Add authentication and authorization.
- Add retrieval and answer evaluation metrics.
- Extract speaker and timestamp metadata during transcript ingestion.

## Example Questions

- Who was assigned API integration?
- What deadlines were discussed?
- What decisions were made?
- What risks were identified?
- Summarize the meeting and cite the relevant sources.
- Show the supporting text for the API integration owner.

# Embedding provider and Ollama
Contracts and adapters for embedding with explicit model identity, dimensions
verified and batch bounded. The embeddings will feed the M3-08/M3-09 index; in
this milestone are not yet written in Qdrant.

## Contract

`packages/core/src/uai_core/embeddings.py`:

- `EmbeddingModel`: `id`, `provider` (`ollama`/`openai-compatible`), `dimension`,
  `version`, `batch_size`.
- `EmbeddingProvider.embed(texts) -> list[list[float]]`.
- `EmbeddingError` / `EmbeddingUnavailable` with stable codes.
- `validate_texts` / `validate_vectors` apply limits and check size,
  number of vectors and finite values.

`EmbeddingModel.index_version` is the SHA-256 of provider, id, version and
size. A change of model, version or size produces a
different `index_version`: M3-09 needs to build/activate a new index version
in a new Qdrant collection ([vector-store.md](vector-store.md)), do not reuse
the existing one.

## Limits and security

- Batch: 1…`batch_size` (maximum 128); non-empty text, maximum 32,000 characters.
- Number of vectors returned = number of texts; each carrier must have exactly
  `dimension` finite values.
- Timeout 30 seconds, no redirects, `trust_env=False`.
- Retry only on timeout/transport error/429/5xx, max 1 by default. A 4xx
  or an invalid response/wrong size will not be retried.
- Errors without bodies, vectors or credentials in the logs.

## Adapter

### Ollama embeddings

`OllamaEmbeddingProvider` calls `POST {base}/api/embed` with
`{"model": ..., "input": [...]}` and reads `embeddings`. There is no API key
necessary. Base default `http://ollama:11434`; the model must already be
downloaded to the Ollama instance.

### OpenAI-compatible embeddings

`OpenAIEmbeddingProvider` calls `POST {base}/embeddings` with
`{"model": ..., "input": [...]}`. If `EMBEDDING_API_KEY` is empty do not send
`Authorization`; with key send Bearer. He also responds for LiteLLM, which remains
behind the same OpenAI-compatible boundary and is not a core dependency.
Results are sorted by `index`, checked for duplicates/missing.

### Ollama chat

`OllamaProvider` implements `/api/chat` in NDJSON streaming. It is selectable in the
runtime with `MODEL_PROVIDER=ollama` and `OLLAMA_BASE_URL` (default
`http://ollama:11434`); does not require cloud key. The OpenAI-compatible provider
remains the default and can use Ollama via `/v1/chat/completions`.

## Configuration

Examples in `configs/models/embedding-ollama.json` and
`configs/models/embedding-openai.json`. Factory variables
`embedding_provider_from_env()` (used by the worker in subsequent milestones):

| Variable | Default | Notes |
| --- | --- | --- |
| `EMBEDDING_PROVIDER` | `ollama` | `ollama` or `openai-compatible` |
| `EMBEDDING_MODEL` | `nomic-embed-text` | model id |
| `EMBEDDING_DIMENSION` | `768` | must match the pattern |
| `EMBEDDING_VERSION` | model id | logical version for the index |
| `EMBEDDING_BATCH_SIZE` | `32` | maximum 128 |
| `EMBEDDING_BASE_URL` | `http://ollama:11434` for Ollama; mandatory for OpenAI | base without `/embeddings` |
| `EMBEDDING_API_KEY` | empty | OpenAI-compatible only |

For Ollama template: `ollama pull nomic-embed-text`. With Ollama it doesn't matter
no cloud key.

## Model change

`index_version` is the index compatibility key. Change provider,
`EMBEDDING_MODEL`, `EMBEDDING_VERSION` or size requires new version
index; the old index should not be reused with a different model. An error of
size is explicit (`embedding_dimension_mismatch`), not silent.

## Evidence

`apps/runtime/tests/test_embeddings.py` covers:

- identity/index version;
- batch, empty text, wrong size and invalid response;
- retry on 429/5xx/timeout, no retry on 4xx;
- OpenAI header and absence of Ollama header;
- sorting by index;
- factory and configuration;
- Ollama chat streaming, usage and fail-closed without `done`/with error.Opt-in testing with real Ollama: set `UAI_OLLAMA_TEST_URL` and
`UAI_EMBEDDING_TEST_MODEL`, then run pytest; otherwise it remains skipped.
Local evidence M3-07: `make test` 221 runtime + 8 workers + 3 skipped (S3/Ollama
real absent), Go race/vet. Opt-in verification performed with Ollama 0.6.8 e
`nomic-embed-text` (768 size): 9/9 embedding tests passed.
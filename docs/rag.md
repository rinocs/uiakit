# RAG Directive, citations and gates
Integration of retrieval into the run, verifiable citations and gate closure
RAG. The recovered content remains **non-authoritative data**: it does not modify system
prompt, policy, authority, or tool.

## Flow

1. The server has `knowledge_base_ids` and selects `builtin.rag`.
2. The gateway, in `Start`, reads the active versions of the authorized KBs and sends
   `retrieval_targets` (KB, collection, index_version, embedding metadata) in the
   internal request. No targets are accepted by the model or the client.
3. The `builtin.rag` directive:
    - requires available KB, target and retriever;
    - performs retrieval for each KB with the KB-only `AccessFilter`;
    - merges, deduplicates, sorts and applies the context budget;
    - assigns `C1`, `C2`, … to the selected chunks;
    - adds an **untrusted reference** block with text and metadata to the user message;
    - saves the citation map in the run's working memory.
4. The built-in guards (system prompt, conversation memory, tool policy, output
   validation) remain mandatory and run after the middleware.
5. `after_model` selects only the quotes actually referenced in the output
   (`[C1]`, `[C2]`, …). Unknown markers do not produce citations.
6. `response.completed` includes `citations[]` with citation_id, chunk_id, KB,
   document_id, hash/version, page and offset. The SSE text remains unchanged.

## Contract quotes

Public `Citation` scheme:

```json
{"citation_id":"C1","chunk_id":"…","knowledge_base_id":"…","document_id":"…",
 "document_hash":"…","document_version":1,"page":1,"start":0,"end":42}
```

A citation is issued only if the chunk has been recovered and the model has it
referenced. Chunk/version/page/offset must match the document
exportable to PostgreSQL. The gateway holds the raw event, then replays it
persistence they maintain citations.

## Prompt injection and authority

The retrieved text is placed in a block labeled as untrusted. It can
contain hostile instructions, but:
- system prompt, assistant, authority, limits and authorized history do not change;
- built-in guards are not selectable/removable from the document;
- tool and scope remain those of the principal;
- quotes and context do not grant access to unauthorized sources.

The defense does not claim to semantically neutralize every prompt injection:
the separation of authority is in the runtime, not in the text.

## Errors

KB without target, no retriever, empty ACL, version/embedding mismatch,
retrieval backend failure or context not insertable fail closed with
`directive_failed`; no context is invented. A run without RAG directive
continues to function normally.

## Gates and tests

- Unit: RAG directive, untrusted context, unchanged authority, missing target,
  citations only used, valid `Citation` payload.
- Public Contract: `Citation` and `RuntimeEvent.payload` document citations.
- E2E `tests/e2e/check_rag.py`:
  - assistant with KB + `builtin.rag`;
  - upload→parse→chunk→embed→Qdrant→query;
  - response with `[C1]` and `citations[]`;
  - each quote compared to the export (chunk/document/version/page/offset);
  - system prompt and server KB unchanged.
- Real gate M1/M2/M3: `make test` 221 runtime + 8 workers + 3 skipped, Go
  race/vet; `make e2e` 22 checks passed (PostgreSQL, Qdrant, worker, runtime).

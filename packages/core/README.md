# uai-core 0.1.0

Contratti Python installabili, senza dipendenze FastAPI, HTTPX o database:

- `Message`, `ModelInput`: input modello immutabili; nessuna credenziale o autorità.
- `ExecutionAuthority`, `ExecutionLimits`, `ExecutionContext`: snapshot protetti.
- `Agent`: protocollo `run(context) -> AsyncIterator[RuntimeEvent]`.
- `AgentRuntime`: crea contesto/working memory per chiamata e pulisce a fine stream,
  errore, cancellazione o chiusura esplicita; il consumer deve chiudere lo stream.
- `ModelProvider`, `ModelChunk`, `ProviderError`: protocollo provider consolidato.
- `RuntimeEvent`: envelope SSE e payload M1 consolidati, senza breaking change.
- `WorkingMemory`: JSON isolato per run, copie detached, massimo 64.000 byte.
- `MemoryProvider`: contratto conversation read/write/delete/retention con scope
  esplicito; nessuna implementazione no-op di mutazioni o semantic memory.

`ExecutionContext.with_messages()` sostituisce solo i messaggi, mantenendo prompt,
modello, authority, limiti e identificatori. Pydantic frozen e tuple/frozenset
impediscono modifiche attraverso le normali API: **non sono una sandbox Python**.
Trusted plugin rimangono codice fidato; l’enforcement dei contesti restituiti dalle
direttive sarà implementato in M2-04. Working memory non concede permessi.

Il runtime mantiene `RunRequest` come DTO HTTP e converte soltanto dopo auth interna.
Il gateway propaga la authority autenticata (M2-02); per compatibilità, richieste
interne M1 senza authority ricevono bootstrap-operator senza scopes/tool grant. Il provider riceve esclusivamente
ModelInput. Il gateway resta owner di PostgreSQL e dei commit della conversazione;
il backend MemoryProvider persistente verrà collegato in M2-06.

## Sviluppo

Dalla root, con le dipendenze runtime già installate:

```bash
python -m pip install -e packages/core
make test
```

CI e immagine runtime installano il package locale. Wheel con `py.typed` e metadata
standard setuptools; nessun accesso al provider richiesto per importare il core.

M2-03 aggiunge `AssistantConfig` e `ModelDefinition` (capability esplicite), entrambi
immutabili. ExecutionContext conserva versione e metadata modello; with_messages
li preserva. ExecutionLimits è consolidato in configuration e resta importabile
da context per compatibilità. Tool/RAG/skills/semantic memory/structured output
non attivabili finché non è implementata la relativa capacità.

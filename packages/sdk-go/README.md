# Universal AI Kit Go SDK

Client Go per la Public API e per lo stream SSE del gateway. Nessuna dipendenza
esterna; usa `context.Context` e `net/http`.

## Uso

```go
client, err := uai.New("http://localhost:8080", os.Getenv("UAI_API_KEY"))
if err != nil {
    log.Fatal(err)
}

ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
defer cancel()

assistants, err := client.ListAssistants(ctx)
if err != nil {
    log.Fatal(err)
}
conversation, err := client.CreateConversation(ctx, uai.ConversationInput{
    AssistantID: assistants[0].ID,
})
if err != nil {
    log.Fatal(err)
}

stream, err := client.SendMessage(ctx, conversation.ID, uai.MessageInput{
    Content: "Riassumi i documenti caricati.",
}, "idem-"+uuid.NewString())
if err != nil {
    log.Fatal(err)
}
defer stream.Close()

for {
    event, err := stream.Next()
    if errors.Is(err, io.EOF) {
        break
    }
    if err != nil {
        log.Fatal(err)
    }
    if event.EventType == "response.delta" {
        var payload uai.TextPayload
        if err := event.DecodePayload(&payload); err != nil {
            log.Fatal(err)
        }
        fmt.Print(payload.Text)
    }
}
```

`SendMessage` richiede una idempotency key esplicita. Ritentare con la stessa
chiave recupera l'esito persistito.

## Terminali ed errori

`Next` restituisce `io.EOF` solo dopo `response.completed`. Un EOF senza evento
terminale produce `*StreamIncompleteError`. `agent.failed` e `agent.cancelled`
restituiscono l'evento insieme a `*AgentFailedError` / `*AgentCancelledError`.
Errori HTTP: `*APIError` con `Status`, `Code` e `Body`. Input/header mancanti:
`*ValidationError`. Altri: `*AbortError`, `*TimeoutError`, `*NetworkError`,
`*StreamProtocolError`, `*ResponseError`.

## Abort, timeout e cancellazione

Il `context` controlla l'intera richiesta SSE. Se viene cancellato o scade, il
client interrompe la lettura e richiede `POST /v1/agent-runs/{id}/cancel` con un
timeout breve e indipendente. `Close` chiude lo stream e il monitor di
cancellazione.

## SSE

`SSEDecoder` è riutilizzabile e accetta chunk arbitrari: frame divisi, UTF-8
spezzato, CRLF, commenti e `data:` multipli. `Parse` non è necessario: il client
lo usa internamente.

## Sviluppo

```bash
cd packages/sdk-go
go test -race ./...
go vet ./...
```

Il test `TestOperationsMatchPublicContract` confronta `Operations` con
`packages/api-contract/public.openapi.json`.

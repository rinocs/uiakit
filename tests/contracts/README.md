# SDK contract matrix

`check_contracts.py` confronta le mappe operazioni dei tre SDK con
`packages/api-contract/public.openapi.json`:

| SDK | File | Comando |
|---|---|---|
| TypeScript | `packages/sdk-typescript/src/operations.ts` | `make test-typescript` |
| Go | `packages/sdk-go/operations.go` | `make test-go-sdk` |
| PHP | `packages/sdk-php/src/Operations.php` | `make test-php` |

Esegue anche il controllo di esistenza di package/esempi/docs dichiarati in
`sdk-matrix.json`. Non sostituisce i test di comportamento dei singoli SDK:
verifica che metodo, path e header obbligatori (`Idempotency-Key`, `If-Match`)
siano identici al contratto pubblico.

```bash
make test-contracts
```

La matrice è volutamente senza dipendenze: può essere eseguita anche prima di
`npm install`/`go test`/`composer install`, mentre le suite complete restano
`make test-typescript`, `make test-go-sdk`, `make test-php`.

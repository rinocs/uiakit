package main

import (
	"bytes"
	"context"
	"errors"
	"os"
	"testing"
)

func TestProviderStoreProfiles(t *testing.T) {
	store := providerTestStore(t)
	ctx := context.WithValue(context.Background(), principalKey{}, Principal{ID: bootstrapPrincipal, Role: "admin"})

	created, err := store.CreateProviderProfile(ctx, ProviderProfile{
		ID: "openai", Name: "OpenAI", Provider: "openai-compatible",
		BaseURL: "https://api.example.com/v1", MaxOutputTokens: 512,
		Models: []ProviderModel{{ID: "alpha"}, {ID: "beta", Capabilities: []string{"tool_calling"}}},
	})
	if err != nil || created.Revision != 1 || created.ConfigSeq != 2 {
		t.Fatalf("create: %+v %v", created, err)
	}
	firstGlobal := providerGlobalRevision(t, store, ctx)
	if created.ConfigSeq != firstGlobal {
		t.Fatalf("first write config_seq %d != global revision %d", created.ConfigSeq, firstGlobal)
	}
	if _, err := store.CreateProviderProfile(ctx, created); !errors.Is(err, ErrConflict) {
		t.Fatalf("duplicate id: %v", err)
	}

	created.Name = "OpenAI EU"
	if _, err := store.UpdateProviderProfile(ctx, "openai", 0, created); !errors.Is(err, ErrConflict) {
		t.Fatalf("stale expected: %v", err)
	}
	updated, err := store.UpdateProviderProfile(ctx, "openai", 1, created)
	if err != nil || updated.Revision != 2 || updated.ConfigSeq != 3 {
		t.Fatalf("update: %+v %v", updated, err)
	}

	// A write to another profile must not conflict with the first one.
	other, err := store.CreateProviderProfile(ctx, ProviderProfile{
		ID: "local", Name: "Local", Provider: "ollama",
		BaseURL: "http://ollama:11434", MaxOutputTokens: 256,
		Models: []ProviderModel{{ID: "llama3.2:3b"}},
	})
	if err != nil || other.ConfigSeq != 4 {
		t.Fatalf("second profile: %+v %v", other, err)
	}
	secondGlobal := providerGlobalRevision(t, store, ctx)
	if other.ConfigSeq != secondGlobal || secondGlobal <= firstGlobal {
		t.Fatalf("second write config_seq %d != global revision %d (first %d)", other.ConfigSeq, secondGlobal, firstGlobal)
	}

	stored, err := store.SetProviderSecret(ctx, "openai", ProviderSecret{
		Source: "stored", Cipher: bytes.Repeat([]byte{7}, 32), Nonce: bytes.Repeat([]byte{1}, 12), KeyVersion: 1,
	})
	if err != nil || len(stored.SecretCipher) != 32 || stored.SecretRef != "" || stored.Revision != 3 {
		t.Fatalf("stored secret: %+v %v", stored, err)
	}
	envRef, err := store.SetProviderSecret(ctx, "openai", ProviderSecret{Source: "env", Ref: "MODEL_API_KEY"})
	if err != nil || envRef.SecretCipher != nil || envRef.SecretRef != "MODEL_API_KEY" {
		t.Fatalf("env secret: %+v %v", envRef, err)
	}

	if applied, err := store.ProviderAppliedRevision(ctx); err != nil || applied != 0 {
		t.Fatalf("applied: %d %v", applied, err)
	}
	if err := store.MarkProviderApplied(ctx, 6); err != nil {
		t.Fatal(err)
	}
	if err := store.MarkProviderApplied(ctx, 2); err != nil {
		t.Fatal(err)
	}
	if applied, _ := store.ProviderAppliedRevision(ctx); applied != 6 {
		t.Fatalf("applied regressed: %d", applied)
	}

	if _, err := store.pool.Exec(ctx,
		`INSERT INTO assistants(id,name,model,system_prompt) VALUES
		 (gen_random_uuid(),'legacy','beta','p'),(gen_random_uuid(),'current','openai/alpha','p')`); err != nil {
		t.Fatal(err)
	}
	for key, want := range map[string]int{
		"openai/alpha": 1, "default/beta": 1, "openai/beta": 0, "local/alpha": 0,
	} {
		if count, err := store.AssistantsUsingModel(ctx, key); err != nil || count != want {
			t.Fatalf("%s: %d %v", key, count, err)
		}
	}

	if err := store.DeleteProviderProfile(ctx, "local"); err != nil {
		t.Fatalf("delete: %v", err)
	}
	if _, err := store.ProviderProfile(ctx, "local"); !errors.Is(err, ErrNotFound) {
		t.Fatalf("deleted profile: %v", err)
	}
}

func providerGlobalRevision(t *testing.T, store *PostgresStore, ctx context.Context) int64 {
	t.Helper()
	var revision int64
	if err := store.pool.QueryRow(ctx, `SELECT revision FROM provider_revision WHERE singleton`).Scan(&revision); err != nil {
		t.Fatalf("read global revision: %v", err)
	}
	return revision
}

func providerTestStore(t *testing.T) *PostgresStore {
	t.Helper()
	url := os.Getenv("UAI_TEST_DATABASE_URL")
	if url == "" {
		t.Skip("UAI_TEST_DATABASE_URL is not set; skipping provider store integration test")
	}
	ctx := context.Background()
	store, err := OpenStore(ctx, url)
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	t.Cleanup(func() { store.pool.Close() })
	for _, table := range []string{"provider_profile_models", "provider_profiles", "assistants"} {
		if _, err := store.pool.Exec(ctx, "TRUNCATE "+table+" CASCADE"); err != nil {
			t.Fatalf("truncate %s: %v", table, err)
		}
	}
	if _, err := store.pool.Exec(ctx, `UPDATE provider_revision SET revision=1, applied_revision=0`); err != nil {
		t.Fatalf("reset provider_revision: %v", err)
	}
	return store
}

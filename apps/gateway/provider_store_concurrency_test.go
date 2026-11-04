package main

import (
	"context"
	"errors"
	"sync"
	"testing"
)

func TestProviderStoreProfileCapIsAtomic(t *testing.T) {
	store := providerTestStore(t)
	ctx := context.WithValue(context.Background(), principalKey{}, Principal{ID: bootstrapPrincipal, Role: "admin"})
	if !validProviderProfileInput("profile-a", "OpenAI", "openai-compatible", "https://api.example.com/v1", 256, []ProviderModel{{ID: "model"}}) {
		t.Fatal("test profile is invalid")
	}
	results := make(chan error, 24)
	var wg sync.WaitGroup
	for i := 0; i < 24; i++ {
		i := i
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, err := store.CreateProviderProfile(ctx, ProviderProfile{
				ID: "profile-" + string(rune('a'+i)), Name: "OpenAI", Provider: "openai-compatible",
				BaseURL: "https://api.example.com/v1", MaxOutputTokens: 256,
				Models: []ProviderModel{{ID: "model"}},
			})
			results <- err
		}()
	}
	wg.Wait()
	close(results)

	succeeded := 0
	tooMany := 0
	for err := range results {
		switch {
		case err == nil:
			succeeded++
		case errors.Is(err, ErrTooManyProfiles):
			tooMany++
		default:
			t.Fatalf("unexpected create error: %T %#v", err, err)
		}
	}
	if succeeded != 20 || tooMany != 4 {
		t.Fatalf("succeeded=%d too_many=%d, want 20 and 4", succeeded, tooMany)
	}
	var count int
	if err := store.pool.QueryRow(ctx, `SELECT count(*) FROM provider_profiles`).Scan(&count); err != nil {
		t.Fatal(err)
	}
	if count != 20 {
		t.Fatalf("stored profile count=%d, want 20", count)
	}
}

package main

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/jackc/pgx/v5"
)

const providerResourceID = "00000000-0000-4000-8000-0000000000f1"

func (s *PostgresStore) ProviderConfiguration(ctx context.Context) (ProviderConfiguration, error) {
	var config ProviderConfiguration
	var models []byte
	err := s.pool.QueryRow(ctx, `SELECT revision, provider, base_url, api_key_ref, max_output_tokens, models
		FROM provider_configuration WHERE singleton`).Scan(
		&config.Revision, &config.Provider, &config.BaseURL, &config.APIKeyRef,
		&config.MaxOutputTokens, &models)
	if errors.Is(err, pgx.ErrNoRows) {
		return ProviderConfiguration{}, ErrNotFound
	}
	if err == nil {
		err = json.Unmarshal(models, &config.Models)
	}
	return config, err
}

func (s *PostgresStore) SaveProviderConfiguration(ctx context.Context, expected int, config ProviderConfiguration) (ProviderConfiguration, error) {
	if !validProviderConfiguration(config) || expected < 0 {
		return config, ErrInvalidConfig
	}
	models, err := json.Marshal(config.Models)
	if err != nil {
		return config, err
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return config, err
	}
	defer tx.Rollback(ctx)

	var revision int
	var updatedBy string
	err = tx.QueryRow(ctx, `SELECT revision FROM provider_configuration WHERE singleton FOR UPDATE`).Scan(&revision)
	switch {
	case errors.Is(err, pgx.ErrNoRows):
		if expected != 0 {
			return config, ErrConflict
		}
		revision = 1
		updatedBy = currentPrincipal(ctx).ID
		_, err = tx.Exec(ctx, `INSERT INTO provider_configuration
			(singleton, revision, provider, base_url, api_key_ref, max_output_tokens, models, updated_by)
			VALUES(true,$1,$2,$3,$4,$5,$6,$7)`,
			revision, config.Provider, config.BaseURL, config.APIKeyRef,
			config.MaxOutputTokens, models, updatedBy)
	case err != nil:
		return config, err
	default:
		if expected != revision {
			return config, ErrConflict
		}
		revision++
		updatedBy = currentPrincipal(ctx).ID
		_, err = tx.Exec(ctx, `UPDATE provider_configuration
			SET revision=$1, provider=$2, base_url=$3, api_key_ref=$4,
			    max_output_tokens=$5, models=$6, updated_at=now(), updated_by=$7
			WHERE singleton`,
			revision, config.Provider, config.BaseURL, config.APIKeyRef,
			config.MaxOutputTokens, models, updatedBy)
	}
	if err != nil {
		return config, err
	}
	ids := make([]string, 0, len(config.Models))
	for _, model := range config.Models {
		ids = append(ids, model.ID)
	}
	err = recordAudit(ctx, tx, AuditRecord{
		ActorID: updatedBy, Action: "provider.updated", TargetID: providerResourceID,
		TargetType: "provider", Outcome: "success",
		Details: map[string]any{
			"revision": revision, "provider": config.Provider,
			"base_url": config.BaseURL, "models": ids,
		},
	})
	if err == nil {
		err = tx.Commit(ctx)
	}
	config.Revision = revision
	return config, err
}

func (s *PostgresStore) AssistantsUsingModel(ctx context.Context, model string) (int, error) {
	var count int
	err := s.pool.QueryRow(ctx, `SELECT count(*) FROM assistants WHERE model=$1`, model).Scan(&count)
	return count, err
}

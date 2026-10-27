package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
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
	alias := ""
	if strings.HasPrefix(model, "default/") {
		alias = strings.TrimPrefix(model, "default/")
	}
	var count int
	err := s.pool.QueryRow(ctx, `SELECT count(*) FROM assistants WHERE model=$1 OR ($2<>'' AND model=$2)`,
		model, alias).Scan(&count)
	return count, err
}

type providerQuerier interface {
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
	Query(ctx context.Context, sql string, args ...any) (pgx.Rows, error)
}

// nextConfigSeq serializes provider profile writes on the singleton
// provider_revision row, advances the global counter, and returns the advanced
// revision to store as config_seq. Migration 017 seeds the row; a missing row
// is an error, never a silent re-seed.
func nextConfigSeq(ctx context.Context, tx pgx.Tx) (int64, error) {
	var revision int64
	err := tx.QueryRow(ctx, `UPDATE provider_revision SET revision=revision+1 WHERE singleton RETURNING revision`).Scan(&revision)
	return revision, err
}

func isUniqueViolation(err error) bool {
	var pgErr *pgconn.PgError
	return errors.As(err, &pgErr) && pgErr.Code == "23505"
}

func scanProviderModels(rows pgx.Rows) ([]ProviderModel, error) {
	defer rows.Close()
	var models []ProviderModel
	for rows.Next() {
		var model ProviderModel
		var contextWindow sql.NullInt64
		if err := rows.Scan(&model.ID, &model.Capabilities, &contextWindow); err != nil {
			return nil, err
		}
		if contextWindow.Valid {
			value := int(contextWindow.Int64)
			model.ContextWindow = &value
		}
		models = append(models, model)
	}
	return models, rows.Err()
}

func scanProviderProfile(ctx context.Context, q providerQuerier, id string) (ProviderProfile, error) {
	var profile ProviderProfile
	var keyVersion sql.NullInt64
	err := q.QueryRow(ctx, `SELECT id, name, kind, base_url, secret_cipher, secret_nonce,
			secret_key_version, secret_ref, max_output_tokens, revision, config_seq
		FROM provider_profiles WHERE id=$1`, id).Scan(
		&profile.ID, &profile.Name, &profile.Provider, &profile.BaseURL,
		&profile.SecretCipher, &profile.SecretNonce, &keyVersion, &profile.SecretRef,
		&profile.MaxOutputTokens, &profile.Revision, &profile.ConfigSeq)
	if errors.Is(err, pgx.ErrNoRows) {
		return ProviderProfile{}, ErrNotFound
	}
	if err != nil {
		return ProviderProfile{}, err
	}
	if keyVersion.Valid {
		profile.SecretKeyVersion = int(keyVersion.Int64)
	}
	rows, err := q.Query(ctx, `SELECT model_id, capabilities, context_window
		FROM provider_profile_models WHERE profile_id=$1 ORDER BY model_id`, id)
	if err != nil {
		return ProviderProfile{}, err
	}
	profile.Models, err = scanProviderModels(rows)
	return profile, err
}

func (s *PostgresStore) ProviderProfiles(ctx context.Context) ([]ProviderProfile, error) {
	rows, err := s.pool.Query(ctx, `SELECT id FROM provider_profiles ORDER BY id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var ids []string
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	profiles := make([]ProviderProfile, 0, len(ids))
	for _, id := range ids {
		profile, err := scanProviderProfile(ctx, s.pool, id)
		if err != nil {
			return nil, err
		}
		profiles = append(profiles, profile)
	}
	return profiles, nil
}

func (s *PostgresStore) ProviderProfile(ctx context.Context, id string) (ProviderProfile, error) {
	return scanProviderProfile(ctx, s.pool, id)
}

func replaceProviderModels(ctx context.Context, tx pgx.Tx, profileID string, models []ProviderModel) error {
	if _, err := tx.Exec(ctx, `DELETE FROM provider_profile_models WHERE profile_id=$1`, profileID); err != nil {
		return err
	}
	for _, model := range models {
		capabilities := model.Capabilities
		if capabilities == nil {
			capabilities = []string{}
		}
		var contextWindow any
		if model.ContextWindow != nil {
			contextWindow = *model.ContextWindow
		}
		if _, err := tx.Exec(ctx, `INSERT INTO provider_profile_models (profile_id, model_id, capabilities, context_window)
			VALUES ($1,$2,$3,$4)`, profileID, model.ID, capabilities, contextWindow); err != nil {
			return err
		}
	}
	return nil
}

func providerModelIDs(models []ProviderModel) []string {
	ids := make([]string, 0, len(models))
	for _, model := range models {
		ids = append(ids, model.ID)
	}
	return ids
}

func (s *PostgresStore) CreateProviderProfile(ctx context.Context, profile ProviderProfile) (ProviderProfile, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return profile, err
	}
	defer tx.Rollback(ctx)

	configSeq, err := nextConfigSeq(ctx, tx)
	if err != nil {
		return profile, err
	}
	var profileCount int
	if err := tx.QueryRow(ctx, `SELECT count(*) FROM provider_profiles`).Scan(&profileCount); err != nil {
		return profile, err
	}
	if profileCount >= 20 {
		return profile, ErrTooManyProfiles
	}
	_, err = tx.Exec(ctx, `INSERT INTO provider_profiles
		(id, name, kind, base_url, max_output_tokens, revision, config_seq, updated_by)
		VALUES ($1,$2,$3,$4,$5,1,$6,$7)`,
		profile.ID, profile.Name, profile.Provider, profile.BaseURL,
		profile.MaxOutputTokens, configSeq, currentPrincipal(ctx).ID)
	if isUniqueViolation(err) {
		return profile, ErrConflict
	}
	if err != nil {
		return profile, err
	}
	if err := replaceProviderModels(ctx, tx, profile.ID, profile.Models); err != nil {
		return profile, err
	}
	err = recordAudit(ctx, tx, AuditRecord{
		ActorID: currentPrincipal(ctx).ID, Action: "provider.created",
		TargetID: providerResourceID, TargetType: "provider", Outcome: "success",
		Details: map[string]any{
			"profile_id": profile.ID, "revision": 1, "kind": profile.Provider,
			"base_url": profile.BaseURL, "models": providerModelIDs(profile.Models),
		},
	})
	if err != nil {
		return profile, err
	}
	if err := tx.Commit(ctx); err != nil {
		return profile, err
	}
	return scanProviderProfile(ctx, s.pool, profile.ID)
}

func (s *PostgresStore) UpdateProviderProfile(ctx context.Context, id string, expected int, profile ProviderProfile) (ProviderProfile, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return ProviderProfile{}, err
	}
	defer tx.Rollback(ctx)

	configSeq, err := nextConfigSeq(ctx, tx)
	if err != nil {
		return ProviderProfile{}, err
	}
	var stored int
	err = tx.QueryRow(ctx, `SELECT revision FROM provider_profiles WHERE id=$1`, id).Scan(&stored)
	if errors.Is(err, pgx.ErrNoRows) {
		return ProviderProfile{}, ErrNotFound
	}
	if err != nil {
		return ProviderProfile{}, err
	}
	if stored != expected {
		return ProviderProfile{}, ErrConflict
	}

	revision := stored + 1
	_, err = tx.Exec(ctx, `UPDATE provider_profiles
		SET name=$1, kind=$2, base_url=$3, max_output_tokens=$4, revision=$5,
		    config_seq=$6, updated_at=now(), updated_by=$7
		WHERE id=$8`,
		profile.Name, profile.Provider, profile.BaseURL, profile.MaxOutputTokens,
		revision, configSeq, currentPrincipal(ctx).ID, id)
	if err != nil {
		return ProviderProfile{}, err
	}
	if err := replaceProviderModels(ctx, tx, id, profile.Models); err != nil {
		return ProviderProfile{}, err
	}
	err = recordAudit(ctx, tx, AuditRecord{
		ActorID: currentPrincipal(ctx).ID, Action: "provider.updated",
		TargetID: providerResourceID, TargetType: "provider", Outcome: "success",
		Details: map[string]any{
			"profile_id": id, "revision": revision, "kind": profile.Provider,
			"base_url": profile.BaseURL, "models": providerModelIDs(profile.Models),
		},
	})
	if err != nil {
		return ProviderProfile{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return ProviderProfile{}, err
	}
	return scanProviderProfile(ctx, s.pool, id)
}

func (s *PostgresStore) DeleteProviderProfile(ctx context.Context, id string) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	if _, err := nextConfigSeq(ctx, tx); err != nil {
		return err
	}
	var revision int
	err = tx.QueryRow(ctx, `SELECT revision FROM provider_profiles WHERE id=$1`, id).Scan(&revision)
	if errors.Is(err, pgx.ErrNoRows) {
		return ErrNotFound
	}
	if err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `DELETE FROM provider_profiles WHERE id=$1`, id); err != nil {
		return err
	}
	err = recordAudit(ctx, tx, AuditRecord{
		ActorID: currentPrincipal(ctx).ID, Action: "provider.deleted",
		TargetID: providerResourceID, TargetType: "provider", Outcome: "success",
		Details: map[string]any{"profile_id": id, "revision": revision},
	})
	if err != nil {
		return err
	}
	return tx.Commit(ctx)
}

func (s *PostgresStore) SetProviderSecret(ctx context.Context, id string, secret ProviderSecret) (ProviderProfile, error) {
	switch secret.Source {
	case "none", "stored", "env":
	default:
		return ProviderProfile{}, ErrInvalidConfig
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return ProviderProfile{}, err
	}
	defer tx.Rollback(ctx)

	configSeq, err := nextConfigSeq(ctx, tx)
	if err != nil {
		return ProviderProfile{}, err
	}
	var stored int
	err = tx.QueryRow(ctx, `SELECT revision FROM provider_profiles WHERE id=$1`, id).Scan(&stored)
	if errors.Is(err, pgx.ErrNoRows) {
		return ProviderProfile{}, ErrNotFound
	}
	if err != nil {
		return ProviderProfile{}, err
	}

	revision := stored + 1
	var cipher, nonce, keyVersion any
	secretRef := ""
	action := "provider.secret.clear"
	switch secret.Source {
	case "stored":
		cipher, nonce, keyVersion = secret.Cipher, secret.Nonce, secret.KeyVersion
		action = "provider.secret.set"
	case "env":
		secretRef = secret.Ref
		action = "provider.secret.set"
	}
	_, err = tx.Exec(ctx, `UPDATE provider_profiles
		SET secret_cipher=$1, secret_nonce=$2, secret_key_version=$3, secret_ref=$4,
		    revision=$5, config_seq=$6, updated_at=now(), updated_by=$7
		WHERE id=$8`,
		cipher, nonce, keyVersion, secretRef, revision, configSeq, currentPrincipal(ctx).ID, id)
	if err != nil {
		return ProviderProfile{}, err
	}
	err = recordAudit(ctx, tx, AuditRecord{
		ActorID: currentPrincipal(ctx).ID, Action: action,
		TargetID: providerResourceID, TargetType: "provider", Outcome: "success",
		Details: map[string]any{"profile_id": id, "revision": revision, "secret_source": secret.Source},
	})
	if err != nil {
		return ProviderProfile{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return ProviderProfile{}, err
	}
	return scanProviderProfile(ctx, s.pool, id)
}

func (s *PostgresStore) ProviderAppliedRevision(ctx context.Context) (int64, error) {
	var applied int64
	err := s.pool.QueryRow(ctx, `SELECT applied_revision FROM provider_revision WHERE singleton`).Scan(&applied)
	if errors.Is(err, pgx.ErrNoRows) {
		return 0, nil
	}
	return applied, err
}

func (s *PostgresStore) MarkProviderApplied(ctx context.Context, revision int64) error {
	_, err := s.pool.Exec(ctx, `UPDATE provider_revision SET applied_revision=$1 WHERE singleton AND applied_revision<$1`, revision)
	return err
}

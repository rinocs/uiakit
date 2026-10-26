package main

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
)

const credentialColumns = "id::text,principal_id,role,scopes,expires_at,revoked_at,created_at"

func scanCredential(row pgx.Row) (Credential, error) {
	var c Credential
	e := row.Scan(&c.ID, &c.PrincipalID, &c.Role, &c.Scopes, &c.ExpiresAt, &c.RevokedAt, &c.CreatedAt)
	return c, e
}
func (s *PostgresStore) Authenticate(ctx context.Context, digest string) (Principal, error) {
	var p Principal
	e := s.pool.QueryRow(ctx, "SELECT id::text,principal_id,role,scopes FROM api_credentials WHERE key_digest=$1 AND revoked_at IS NULL AND expires_at>clock_timestamp()", digest).Scan(&p.CredentialID, &p.ID, &p.Role, &p.Scopes)
	if errors.Is(e, pgx.ErrNoRows) {
		return p, ErrUnauthorized
	}
	if e == nil && !validScopes(p.Role, p.Scopes) {
		return Principal{}, ErrUnauthorized
	}
	return p, e
}
func (s *PostgresStore) HasActiveAdmin(ctx context.Context) (bool, error) {
	var exists bool
	e := s.pool.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM api_credentials WHERE role='admin' AND 'credentials:write'=ANY(scopes) AND revoked_at IS NULL AND expires_at>clock_timestamp())").Scan(&exists)
	return exists, e
}
func (s *PostgresStore) Credentials(ctx context.Context) ([]Credential, error) {
	if !currentPrincipal(ctx).allows("credentials:read") {
		return nil, ErrForbidden
	}
	rows, e := s.pool.Query(ctx, "SELECT "+credentialColumns+" FROM api_credentials ORDER BY created_at,id")
	if e != nil {
		return nil, e
	}
	defer rows.Close()
	out := []Credential{}
	for rows.Next() {
		c, e := scanCredential(rows)
		if e != nil {
			return nil, e
		}
		out = append(out, c)
	}
	return out, rows.Err()
}

// Serialize credential mutations and recheck the authorizing key after acquiring
// the lock. Concurrent admins cannot revoke one another using stale authority.
func (s *PostgresStore) credentialWrite(ctx context.Context) (pgx.Tx, error) {
	return s.administrativeWrite(ctx, "credentials:write")
}

func (s *PostgresStore) administrativeWrite(ctx context.Context, scope string) (pgx.Tx, error) {
	actor := currentPrincipal(ctx)
	if !actor.allows(scope) {
		return nil, ErrForbidden
	}
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return nil, e
	}
	_, e = tx.Exec(ctx, "SELECT pg_advisory_xact_lock(714202)")
	if e == nil && actor.CredentialID != "" {
		var role string
		var scopes []string
		e = tx.QueryRow(ctx, "SELECT role,scopes FROM api_credentials WHERE id=$1 AND principal_id=$2 AND revoked_at IS NULL AND expires_at>clock_timestamp()", actor.CredentialID, actor.ID).Scan(&role, &scopes)
		if errors.Is(e, pgx.ErrNoRows) {
			e = ErrUnauthorized
		}
		if e == nil && !(Principal{Role: role, Scopes: scopes}).allows(scope) {
			e = ErrForbidden
		}
	} else if e == nil && actor.ID != bootstrapPrincipal {
		e = ErrUnauthorized
	}
	if e != nil {
		tx.Rollback(ctx)
		return nil, e
	}
	return tx, nil
}
func (s *PostgresStore) CreateCredential(ctx context.Context, c Credential, digest string) (Credential, error) {
	if !validScopes(c.Role, c.Scopes) {
		return c, ErrForbidden
	}
	tx, e := s.credentialWrite(ctx)
	if e != nil {
		return c, e
	}
	defer tx.Rollback(ctx)
	if c.PrincipalID == "" {
		c.PrincipalID = newID()
		_, e = tx.Exec(ctx, "INSERT INTO principals(id) VALUES($1)", c.PrincipalID)
	} else {
		var exists bool
		e = tx.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM principals WHERE id=$1)", c.PrincipalID).Scan(&exists)
		if e == nil && !exists {
			e = ErrNotFound
		}
	}
	if e != nil {
		return c, e
	}
	_, e = tx.Exec(ctx, "INSERT INTO api_credentials(id,principal_id,role,scopes,key_digest,expires_at,created_at) VALUES($1,$2,$3,$4,$5,$6,$7)", c.ID, c.PrincipalID, c.Role, c.Scopes, digest, c.ExpiresAt, c.CreatedAt)
	if e == nil {
		e = recordAudit(ctx, tx, AuditRecord{
			ActorID: currentPrincipal(ctx).ID, Action: "credential.created", TargetID: c.ID,
			TargetType: "credential", Outcome: "success",
			Details: map[string]any{"principal_id": c.PrincipalID, "role": c.Role,
				"scopes": c.Scopes},
		})
	}
	if e == nil {
		e = tx.Commit(ctx)
	}
	return c, e
}
func (s *PostgresStore) mutateCredential(ctx context.Context, id, digest string, expiry time.Time, revoke bool) (Credential, error) {
	if id == currentPrincipal(ctx).CredentialID {
		return Credential{}, ErrConflict
	}
	tx, e := s.credentialWrite(ctx)
	if e != nil {
		return Credential{}, e
	}
	defer tx.Rollback(ctx)
	c, e := scanCredential(tx.QueryRow(ctx, "SELECT "+credentialColumns+" FROM api_credentials WHERE id=$1 FOR UPDATE", id))
	if errors.Is(e, pgx.ErrNoRows) {
		return c, ErrNotFound
	}
	if e != nil {
		return c, e
	}
	action := "credential.rotated"
	if revoke {
		if c.RevokedAt != nil {
			return c, tx.Commit(ctx)
		}
		now := time.Now().UTC()
		c.RevokedAt = &now
		action = "credential.revoked"
		_, e = tx.Exec(ctx, "UPDATE api_credentials SET revoked_at=$2 WHERE id=$1", id, now)
	} else {
		if c.RevokedAt != nil {
			return c, ErrConflict
		}
		c.ExpiresAt = expiry
		_, e = tx.Exec(ctx, "UPDATE api_credentials SET key_digest=$2,expires_at=$3 WHERE id=$1", id, digest, expiry)
	}
	if e == nil {
		e = recordAudit(ctx, tx, AuditRecord{
			ActorID: currentPrincipal(ctx).ID, Action: action, TargetID: id,
			TargetType: "credential", Outcome: "success",
			Details: map[string]any{"principal_id": c.PrincipalID, "role": c.Role,
				"scopes": c.Scopes},
		})
	}
	if e == nil {
		e = tx.Commit(ctx)
	}
	return c, e
}
func (s *PostgresStore) RotateCredential(ctx context.Context, id, digest string, expiry time.Time) (Credential, error) {
	return s.mutateCredential(ctx, id, digest, expiry, false)
}
func (s *PostgresStore) RevokeCredential(ctx context.Context, id string) error {
	_, e := s.mutateCredential(ctx, id, "", time.Time{}, true)
	return e
}

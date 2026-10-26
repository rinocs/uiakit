package main

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"
)

func (s *PostgresStore) WidgetTarget(ctx context.Context, assistantID, conversationID string) error {
	principal := currentPrincipal(ctx)
	var exists bool
	err := s.pool.QueryRow(ctx, `SELECT EXISTS(
		SELECT 1 FROM conversations c JOIN assistants a ON a.id=c.assistant_id
		WHERE c.id::text=$1 AND a.id::text=$2 AND (c.owner_id=$3 OR $4)
	)`, conversationID, assistantID, principal.ID, principal.isAdmin()).Scan(&exists)
	if err != nil {
		return err
	}
	if !exists {
		return ErrNotFound
	}
	return nil
}

func (s *PostgresStore) CreateWidgetToken(ctx context.Context, token WidgetToken, digest string) (WidgetToken, error) {
	tx, err := s.administrativeWrite(ctx, "widget-tokens:write")
	if err != nil {
		return token, err
	}
	defer tx.Rollback(ctx)
	if _, err = tx.Exec(ctx, `INSERT INTO principals(id) VALUES($1) ON CONFLICT DO NOTHING`, "widget:"+token.ID); err != nil {
		return token, err
	}
	_, err = tx.Exec(ctx, `INSERT INTO widget_tokens(
		id,token_digest,assistant_id,conversation_id,subject,scopes,origin,expires_at,created_at,created_by
	) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)`,
		token.ID, digest, token.AssistantID, token.ConversationID, token.Subject,
		token.Scopes, token.Origin, token.ExpiresAt, token.CreatedAt, token.CreatedBy)
	if err == nil {
		err = recordAudit(ctx, tx, AuditRecord{
			ActorID: currentPrincipal(ctx).ID, Action: "widget_token.created", TargetID: token.ID,
			TargetType: "widget_token", Outcome: "success",
			Details: map[string]any{
				"assistant_id": token.AssistantID, "conversation_id": token.ConversationID,
				"subject": token.Subject, "origin": token.Origin,
				"scopes": token.Scopes, "expires_at": token.ExpiresAt,
			},
		})
	}
	if err == nil {
		err = tx.Commit(ctx)
	}
	return token, err
}

func (s *PostgresStore) AuthenticateWidget(ctx context.Context, digest string) (Principal, error) {
	var token WidgetToken
	err := s.pool.QueryRow(ctx, `SELECT id::text,assistant_id::text,conversation_id::text,
		subject,scopes,origin,expires_at,revoked_at,created_at,created_by
		FROM widget_tokens
		WHERE token_digest=$1 AND revoked_at IS NULL AND expires_at>clock_timestamp()`, digest).
		Scan(&token.ID, &token.AssistantID, &token.ConversationID, &token.Subject,
			&token.Scopes, &token.Origin, &token.ExpiresAt, &token.RevokedAt, &token.CreatedAt, &token.CreatedBy)
	if errors.Is(err, pgx.ErrNoRows) {
		return Principal{}, ErrUnauthorized
	}
	if err != nil {
		return Principal{}, err
	}
	if !validScopes("widget", token.Scopes) {
		return Principal{}, ErrUnauthorized
	}
	return Principal{
		ID:     "widget:" + token.ID,
		Role:   "widget",
		Scopes: token.Scopes,
		Widget: &WidgetBinding{
			TokenID: token.ID, AssistantID: token.AssistantID,
			ConversationID: token.ConversationID, Origin: token.Origin,
		},
	}, nil
}

func (s *PostgresStore) RevokeWidgetToken(ctx context.Context, id string) error {
	tx, err := s.administrativeWrite(ctx, "widget-tokens:write")
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	principal := currentPrincipal(ctx)
	tag, err := tx.Exec(ctx, `UPDATE widget_tokens SET revoked_at=now()
		WHERE id=$1 AND revoked_at IS NULL AND (created_by=$2 OR $3)`,
		id, principal.ID, principal.isAdmin())
	if err == nil && tag.RowsAffected() == 0 {
		err = ErrNotFound
	}
	if err == nil {
		err = recordAudit(ctx, tx, AuditRecord{
			ActorID: principal.ID, Action: "widget_token.revoked", TargetID: id,
			TargetType: "widget_token", Outcome: "success",
		})
	}
	if err == nil {
		err = tx.Commit(ctx)
	}
	return err
}

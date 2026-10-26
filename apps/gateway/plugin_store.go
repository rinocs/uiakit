package main

import (
	"bytes"
	"context"
	"encoding/json"
	"slices"
)

func (s *PostgresStore) PluginConfiguration(ctx context.Context) (PluginConfiguration, error) {
	var result PluginConfiguration
	var data []byte
	err := s.pool.QueryRow(ctx, "SELECT revision,settings FROM plugin_configuration WHERE singleton=true").Scan(&result.Revision, &data)
	if err == nil {
		err = json.Unmarshal(data, &result.Settings)
	}
	return result, err
}
func (s *PostgresStore) UpdatePluginConfiguration(ctx context.Context, expected int, settings map[string]PluginSetting) (PluginConfiguration, error) {
	if !validPluginSettings(settings) {
		return PluginConfiguration{}, ErrInvalidConfig
	}
	// Reuse the administrative credential lock, rechecking role/scope after lock acquisition.
	tx, err := s.administrativeWrite(ctx, "plugins:write")
	if err != nil {
		return PluginConfiguration{}, err
	}
	defer tx.Rollback(ctx)
	var revision int
	var oldData []byte
	err = tx.QueryRow(ctx, "SELECT revision,settings FROM plugin_configuration WHERE singleton=true FOR UPDATE").Scan(&revision, &oldData)
	if err != nil {
		return PluginConfiguration{}, err
	}
	if revision != expected {
		return PluginConfiguration{}, ErrPreconditionFailed
	}
	var old map[string]PluginSetting
	if err = json.Unmarshal(oldData, &old); err != nil {
		return PluginConfiguration{}, err
	}
	changed := []string{}
	for key, value := range settings {
		previous, exists := old[key]
		if !exists || previous.Enabled != value.Enabled || !equalPluginJSON(previous.Config, value.Config) {
			changed = append(changed, key)
		}
	}
	for key := range old {
		if _, exists := settings[key]; !exists {
			changed = append(changed, key)
		}
	}
	slices.Sort(changed)
	data, err := json.Marshal(settings)
	if err != nil {
		return PluginConfiguration{}, err
	}
	revision++
	_, err = tx.Exec(ctx, "UPDATE plugin_configuration SET revision=$1,settings=$2,updated_by=$3,updated_at=now() WHERE singleton=true", revision, data, currentPrincipal(ctx).ID)
	if err == nil {
		_, err = tx.Exec(ctx, "INSERT INTO plugin_configuration_audit(revision,actor_id,changed_plugin_ids) VALUES($1,$2,$3)", revision, currentPrincipal(ctx).ID, changed)
	}
	if err == nil {
		err = tx.Commit(ctx)
	}
	return PluginConfiguration{Revision: revision, Settings: settings}, err
}
func equalPluginJSON(left, right json.RawMessage) bool {
	var a, b any
	leftDecoder := json.NewDecoder(bytes.NewReader(left))
	leftDecoder.UseNumber()
	rightDecoder := json.NewDecoder(bytes.NewReader(right))
	rightDecoder.UseNumber()
	if leftDecoder.Decode(&a) != nil || rightDecoder.Decode(&b) != nil {
		return false
	}
	aa, _ := json.Marshal(a)
	bb, _ := json.Marshal(b)
	return string(aa) == string(bb)
}

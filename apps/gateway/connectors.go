package main

import (
	"regexp"
	"strings"
)

var connectorIDPattern = regexp.MustCompile(`^[a-z][a-z0-9_-]{0,99}$`)

func (tool ToolDefinition) connectorIDs() []string {
	ids := make([]string, 0, 1)
	for _, permission := range tool.Permissions {
		if strings.HasPrefix(permission, "connector:") {
			ids = append(ids, strings.TrimPrefix(permission, "connector:"))
		}
	}
	return ids
}

// validateConnector keeps the catalog free of unbound HTTP/MCP tools and of
// mutating HTTP tools until the durable execution path lands in M4-05.
func (tool ToolDefinition) validateConnector() error {
	ids := tool.connectorIDs()
	switch tool.Executor {
	case "builtin":
		if len(ids) != 0 {
			return ErrInvalidConfig
		}
	case "http", "isolated":
		if len(ids) != 1 || !connectorIDPattern.MatchString(ids[0]) || tool.RiskLevel != "read_only" {
			return ErrInvalidConfig
		}
	case "mcp":
		if len(ids) != 1 || !connectorIDPattern.MatchString(ids[0]) {
			return ErrInvalidConfig
		}
	}
	return nil
}

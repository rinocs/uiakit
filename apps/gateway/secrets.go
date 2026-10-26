package main

import (
	"errors"
	"io"
	"os"
	"strings"
	"unicode/utf8"
)

var errSecretConfiguration = errors.New("invalid secret configuration")

const maxSecretFileBytes = 65536

// secretFromEnv resolves NAME or NAME_FILE. An empty NAME is treated as unset
// so a mounted file remains usable; setting both non-empty sources is an error.
func secretFromEnv(name string) (string, error) {
	value, valueSet := os.LookupEnv(name)
	path, pathSet := os.LookupEnv(name + "_FILE")
	if valueSet && value == "" {
		valueSet = false
	}
	if pathSet && path == "" {
		pathSet = false
	}
	if valueSet && pathSet {
		return "", errSecretConfiguration
	}
	if pathSet {
		return readSecretFile(path)
	}
	if !valueSet {
		return "", nil
	}
	return cleanSecret(value)
}

func readSecretFile(path string) (string, error) {
	if path == "" || len(path) > 1024 || !strings.HasPrefix(path, "/") {
		return "", errSecretConfiguration
	}
	for _, char := range path {
		if char < 0x21 || char > 0x7e {
			return "", errSecretConfiguration
		}
	}
	file, err := os.Open(path)
	if err != nil {
		return "", errSecretConfiguration
	}
	defer file.Close()
	data, err := io.ReadAll(io.LimitReader(file, maxSecretFileBytes+1))
	if err != nil || len(data) > maxSecretFileBytes {
		return "", errSecretConfiguration
	}
	if !utf8.Valid(data) {
		return "", errSecretConfiguration
	}
	return cleanSecret(string(data))
}

func cleanSecret(value string) (string, error) {
	value = strings.TrimSuffix(value, "\n")
	value = strings.TrimSuffix(value, "\r")
	if value == "" || len(value) > 8192 || strings.ContainsAny(value, "\r\n\x00") {
		return "", errSecretConfiguration
	}
	return value, nil
}

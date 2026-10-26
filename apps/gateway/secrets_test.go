package main

import (
	"errors"
	"os"
	"strings"
	"testing"
)

func writeTestFile(path, content string) error {
	return os.WriteFile(path, []byte(content), 0o600)
}

func TestSecretFromEnv(t *testing.T) {
	t.Setenv("UAI_TEST_SECRET", "from-env")
	if value, err := secretFromEnv("UAI_TEST_SECRET"); err != nil || value != "from-env" {
		t.Fatalf("env: %q %v", value, err)
	}
}

func TestSecretFromFile(t *testing.T) {
	path := t.TempDir() + "/secret"
	if err := writeTestFile(path, "from-file\n"); err != nil {
		t.Fatal(err)
	}
	t.Setenv("UAI_TEST_SECRET_FILE", path)
	if value, err := secretFromEnv("UAI_TEST_SECRET"); err != nil || value != "from-file" {
		t.Fatalf("file: %q %v", value, err)
	}
}

func TestSecretSourcesConflict(t *testing.T) {
	path := t.TempDir() + "/secret"
	if err := writeTestFile(path, "file"); err != nil {
		t.Fatal(err)
	}
	t.Setenv("UAI_TEST_SECRET", "env")
	t.Setenv("UAI_TEST_SECRET_FILE", path)
	if _, err := secretFromEnv("UAI_TEST_SECRET"); !errors.Is(err, errSecretConfiguration) {
		t.Fatalf("expected conflict, got %v", err)
	}
}

func TestOptionalSecretMissing(t *testing.T) {
	if value, err := secretFromEnv("UAI_TEST_ABSENT"); err != nil || value != "" {
		t.Fatalf("missing: %q %v", value, err)
	}
}

func TestSecretFileInvalid(t *testing.T) {
	for _, content := range []string{"", "line\nbreak", "nul\x00"} {
		path := t.TempDir() + "/secret"
		if err := writeTestFile(path, content); err != nil {
			t.Fatal(err)
		}
		t.Setenv("UAI_TEST_SECRET_FILE", path)
		if _, err := secretFromEnv("UAI_TEST_SECRET"); err == nil {
			t.Fatalf("content %q accepted", content)
		}
	}
}

func TestSecretFilePathValidation(t *testing.T) {
	for _, path := range []string{"relative", "/run/secret token"} {
		t.Setenv("UAI_TEST_SECRET_FILE", path)
		if _, err := secretFromEnv("UAI_TEST_SECRET"); err == nil {
			t.Fatalf("path %q accepted", path)
		}
	}
	t.Setenv("UAI_TEST_SECRET_FILE", "")
	if value, err := secretFromEnv("UAI_TEST_SECRET"); err != nil || value != "" {
		t.Fatalf("empty file path: %q %v", value, err)
	}
}

func TestSecretFileTooLarge(t *testing.T) {
	path := t.TempDir() + "/secret"
	if err := writeTestFile(path, strings.Repeat("a", 70000)); err != nil {
		t.Fatal(err)
	}
	t.Setenv("UAI_TEST_SECRET_FILE", path)
	if _, err := secretFromEnv("UAI_TEST_SECRET"); err == nil {
		t.Fatal("oversized secret accepted")
	}
}

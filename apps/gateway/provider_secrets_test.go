package main

import (
	"bytes"
	"crypto/rand"
	"encoding/base64"
	"errors"
	"testing"
)

func testBox(t *testing.T) *secretBox {
	t.Helper()
	key := make([]byte, 32)
	if _, err := rand.Read(key); err != nil {
		t.Fatal(err)
	}
	box, err := newSecretBox(base64.StdEncoding.EncodeToString(key))
	if err != nil || box == nil {
		t.Fatalf("box: %v", err)
	}
	return box
}

func TestSecretBoxRoundTripAndBinding(t *testing.T) {
	box := testBox(t)
	cipher, nonce, err := box.seal("openai", "sk-test-value")
	if err != nil || len(nonce) != 12 || len(cipher) != len("sk-test-value")+16 {
		t.Fatalf("seal: %v nonce=%d cipher=%d", err, len(nonce), len(cipher))
	}
	plain, err := box.open("openai", cipher, nonce, providerSecretKeyVersion)
	if err != nil || plain != "sk-test-value" {
		t.Fatalf("open: %q %v", plain, err)
	}
	if _, err := box.open("other", cipher, nonce, providerSecretKeyVersion); !errors.Is(err, errSecretUnreadable) {
		t.Fatalf("profile binding: %v", err)
	}
	tampered := bytes.Clone(cipher)
	tampered[len(tampered)-1] ^= 0x01
	if _, err := box.open("openai", tampered, nonce, providerSecretKeyVersion); !errors.Is(err, errSecretUnreadable) {
		t.Fatalf("tamper: %v", err)
	}
	if _, err := box.open("openai", cipher, nonce, 2); !errors.Is(err, errSecretUnreadable) {
		t.Fatalf("version: %v", err)
	}
}

func TestSecretBoxConfiguration(t *testing.T) {
	if box, err := newSecretBox(""); box != nil || err != nil {
		t.Fatalf("absent key: %v", err)
	}
	for _, value := range []string{"not-base64!", base64.StdEncoding.EncodeToString(make([]byte, 31))} {
		if _, err := newSecretBox(value); !errors.Is(err, errSecretConfiguration) {
			t.Fatalf("invalid key %q: %v", value, err)
		}
	}
	if _, _, err := (*secretBox)(nil).seal("openai", "value"); !errors.Is(err, errSecretKeyUnavailable) {
		t.Fatalf("nil box: %v", err)
	}
}

func TestSecretBoxRejectsOutOfContractValues(t *testing.T) {
	box := testBox(t)
	for _, value := range []string{"", "line\nbreak", "carriage\rreturn", "nul\x00byte", string([]byte{0xff}), string(make([]byte, 4097))} {
		if _, _, err := box.seal("openai", value); !errors.Is(err, errSecretValueInvalid) {
			t.Fatalf("value %.20q: %v", value, err)
		}
	}
	cipher, nonce, err := box.seal("openai", "first")
	if err != nil {
		t.Fatal(err)
	}
	second, secondNonce, err := box.seal("openai", "first")
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Equal(nonce, secondNonce) || bytes.Equal(cipher, second) {
		t.Fatal("nonce reuse")
	}
}

func TestSecretBoxRejectsMalformedNonce(t *testing.T) {
	box := testBox(t)
	cipher, _, err := box.seal("openai", "value")
	if err != nil {
		t.Fatal(err)
	}
	for _, nonce := range [][]byte{make([]byte, 11), make([]byte, 13)} {
		if _, err := box.open("openai", cipher, nonce, providerSecretKeyVersion); !errors.Is(err, errSecretUnreadable) {
			t.Fatalf("nonce len=%d: %v", len(nonce), err)
		}
	}
}

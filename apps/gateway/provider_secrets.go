package main

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/base64"
	"errors"
	"io"
	"strings"
	"unicode/utf8"
)

const (
	providerSecretKeyVersion = 1
	maxProviderSecretBytes   = 4096
)

var (
	errSecretKeyUnavailable = errors.New("secret key unavailable")
	errSecretUnreadable     = errors.New("secret unreadable")
	errSecretValueInvalid   = errors.New("invalid secret value")
)

// secretBox seals and opens provider credential values with AES-256-GCM. The
// KEK is resolved elsewhere and passed in as a base64-std 32-byte key; the box
// never reads the environment itself. A nil box represents an absent KEK and
// fails closed rather than returning credentials in the clear.
type secretBox struct {
	aead cipher.AEAD
}

func newSecretBox(encoded string) (*secretBox, error) {
	if encoded == "" {
		return nil, nil
	}
	key, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil || len(key) != 32 {
		return nil, errSecretConfiguration
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, errSecretConfiguration
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, errSecretConfiguration
	}
	return &secretBox{aead: aead}, nil
}

func providerSecretAAD(profileID string) []byte {
	return []byte("provider-credential:v1:" + profileID)
}

func (b *secretBox) seal(profileID, plaintext string) (cipher, nonce []byte, err error) {
	if b == nil || b.aead == nil {
		return nil, nil, errSecretKeyUnavailable
	}
	if plaintext == "" || len(plaintext) > maxProviderSecretBytes || strings.ContainsAny(plaintext, "\r\n\x00") || !utf8.ValidString(plaintext) {
		return nil, nil, errSecretValueInvalid
	}
	nonce = make([]byte, b.aead.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, nil, err
	}
	cipher = b.aead.Seal(nil, nonce, []byte(plaintext), providerSecretAAD(profileID))
	return cipher, nonce, nil
}

func (b *secretBox) open(profileID string, cipher, nonce []byte, version int) (string, error) {
	if version != providerSecretKeyVersion {
		return "", errSecretUnreadable
	}
	if b == nil || b.aead == nil {
		return "", errSecretUnreadable
	}
	if len(nonce) != b.aead.NonceSize() {
		return "", errSecretUnreadable
	}
	plaintext, err := b.aead.Open(nil, nonce, cipher, providerSecretAAD(profileID))
	if err != nil {
		return "", errSecretUnreadable
	}
	return string(plaintext), nil
}

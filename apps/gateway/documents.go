package main

import (
	"archive/zip"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"log"
	"mime"
	"net/http"
	"path"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
)

const (
	maxDocumentBytes      = 20 << 20
	maxMultipartOverhead  = 1 << 20
	documentUploadTimeout = 30 * time.Second
)

var ErrStorageUnavailable = errors.New("storage_unavailable")

type Document struct {
	ID              string    `json:"id"`
	KnowledgeBaseID string    `json:"knowledge_base_id"`
	Filename        string    `json:"filename"`
	Title           string    `json:"title"`
	MIMEType        string    `json:"mime_type"`
	SizeBytes       int64     `json:"size_bytes"`
	SHA256          string    `json:"sha256"`
	BlobKey         string    `json:"blob_key,omitempty"`
	CreatedAt       time.Time `json:"created_at"`
	IngestionState  string    `json:"ingestion_state"`
}

func (d Document) validate() error {
	if !validID(d.KnowledgeBaseID) || strings.TrimSpace(d.Filename) == "" || len(d.Filename) > 255 ||
		len(d.Title) > 200 || d.SizeBytes < 1 || len(d.SHA256) != 64 || d.BlobKey == "" {
		return ErrInvalidConfig
	}
	if _, ok := documentMIME[d.MIMEType]; !ok {
		return ErrInvalidConfig
	}
	return nil
}

var documentMIME = map[string]bool{
	"text/plain":      true,
	"text/markdown":   true,
	"text/html":       true,
	"application/pdf": true,
	"application/vnd.openxmlformats-officedocument.wordprocessingml.document": true,
}

func mediaType(value string) string {
	parsed, _, err := mime.ParseMediaType(value)
	if err != nil {
		return ""
	}
	return strings.ToLower(parsed)
}

func sniffMIME(data []byte) string {
	if len(data) == 0 {
		return ""
	}
	head := data
	if len(head) > 512 {
		head = head[:512]
	}
	return mediaType(http.DetectContentType(head))
}

func validateDocumentMIME(declared string, data []byte) (string, error) {
	declared = mediaType(declared)
	if !documentMIME[declared] || len(data) == 0 {
		return "", ErrInvalidConfig
	}
	sniffed := sniffMIME(data)
	switch declared {
	case "text/plain":
		if !strings.HasPrefix(sniffed, "text/plain") {
			return "", ErrInvalidConfig
		}
	case "text/markdown":
		if !strings.HasPrefix(sniffed, "text/plain") {
			return "", ErrInvalidConfig
		}
	case "text/html":
		if sniffed != "text/html" {
			return "", ErrInvalidConfig
		}
	case "application/pdf":
		if !bytes.HasPrefix(data, []byte("%PDF-")) {
			return "", ErrInvalidConfig
		}
	case "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
		if sniffed != "application/zip" && sniffed != "application/octet-stream" {
			return "", ErrInvalidConfig
		}
		if err := validateDocx(data); err != nil {
			return "", ErrInvalidConfig
		}
	}
	return declared, nil
}

func validateDocx(data []byte) error {
	reader, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil || len(reader.File) > 1000 {
		return ErrInvalidConfig
	}
	required := map[string]bool{}
	var total uint64
	for _, file := range reader.File {
		if file.Flags&1 != 0 || strings.Contains(file.Name, "\\") ||
			strings.HasPrefix(file.Name, "/") || strings.Contains(file.Name, "..") ||
			file.UncompressedSize64 > 32<<20 {
			return ErrInvalidConfig
		}
		if strings.EqualFold(path.Base(file.Name), "vbaProject.bin") {
			return ErrInvalidConfig
		}
		total += file.UncompressedSize64
		if total > 64<<20 {
			return ErrInvalidConfig
		}
		if file.Name == "[Content_Types].xml" || file.Name == "word/document.xml" {
			required[file.Name] = true
		}
	}
	if !required["[Content_Types].xml"] || !required["word/document.xml"] {
		return ErrInvalidConfig
	}
	return nil
}

func safeFilename(value string) (string, error) {
	value = strings.ReplaceAll(value, "\\", "/")
	name := path.Base(value)
	if name == "" || name == "." || name == ".." || len(name) > 255 ||
		strings.ContainsAny(name, "\x00\r\n") {
		return "", ErrInvalidConfig
	}
	return name, nil
}

func (s *server) documentRoutes(r chi.Router) {
	r.With(requireScope("documents:read")).Get("/v1/documents", s.listDocuments)
	r.With(requireScope("documents:write")).Post("/v1/documents", s.uploadDocument)
	r.With(requireScope("documents:read")).Get("/v1/documents/{id}", s.getDocument)
	r.With(requireScope("documents:write")).Delete("/v1/documents/{id}", s.deleteDocument)
}

func (s *server) listDocuments(w http.ResponseWriter, r *http.Request) {
	kbID := r.URL.Query().Get("knowledge_base_id")
	if kbID != "" {
		if !validID(kbID) {
			problem(w, 422, "invalid_id")
			return
		}
		if _, e := s.store.KnowledgeBase(r.Context(), kbID); e != nil {
			storeError(w, e)
			return
		}
	}
	docs, e := s.store.Documents(r.Context(), kbID)
	if e != nil {
		storeError(w, e)
		return
	}
	respond(w, 200, docs)
}

func (s *server) getDocument(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	if !validID(id) {
		problem(w, 422, "invalid_id")
		return
	}
	doc, e := s.store.Document(r.Context(), id)
	if e != nil {
		storeError(w, e)
		return
	}
	respond(w, 200, doc)
}

func (s *server) uploadDocument(w http.ResponseWriter, r *http.Request) {
	r.Body = http.MaxBytesReader(w, r.Body, maxDocumentBytes+maxMultipartOverhead)
	if e := r.ParseMultipartForm(1 << 20); e != nil {
		var tooLarge *http.MaxBytesError
		if errors.As(e, &tooLarge) {
			problem(w, 413, "file_too_large")
		} else {
			problem(w, 422, "invalid_multipart")
		}
		return
	}
	defer r.MultipartForm.RemoveAll()
	kbID := r.FormValue("knowledge_base_id")
	if !validID(kbID) {
		problem(w, 422, "invalid_id")
		return
	}
	file, header, e := r.FormFile("file")
	if e != nil {
		problem(w, 422, "file_required")
		return
	}
	defer file.Close()
	data, e := io.ReadAll(io.LimitReader(file, maxDocumentBytes+1))
	if e != nil {
		problem(w, 422, "invalid_file")
		return
	}
	if len(data) > maxDocumentBytes {
		problem(w, 413, "file_too_large")
		return
	}
	declared := header.Header.Get("Content-Type")
	mimeType, e := validateDocumentMIME(declared, data)
	if e != nil {
		problem(w, 415, "unsupported_media_type")
		return
	}
	filename, e := safeFilename(header.Filename)
	if e != nil {
		problem(w, 422, "invalid_filename")
		return
	}
	title := strings.TrimSpace(r.FormValue("title"))
	if title == "" {
		title = filename
	}
	if len(title) > 200 {
		problem(w, 422, "invalid_title")
		return
	}
	if _, e = s.store.KnowledgeBase(r.Context(), kbID); e != nil {
		storeError(w, e)
		return
	}
	sum := sha256.Sum256(data)
	hash := hex.EncodeToString(sum[:])
	if existing, e := s.store.DocumentByHash(r.Context(), kbID, hash); e == nil {
		w.Header().Set("X-Deduplicated", "true")
		respond(w, 200, existing)
		return
	} else if !errors.Is(e, ErrNotFound) {
		storeError(w, e)
		return
	}
	key := "documents/" + kbID + "/" + newID()
	ctx, cancel := context.WithTimeout(r.Context(), documentUploadTimeout)
	defer cancel()
	if e = s.putBlob(ctx, key, data); e != nil {
		storeError(w, e)
		return
	}
	doc := Document{KnowledgeBaseID: kbID, Filename: filename, Title: title, MIMEType: mimeType,
		SizeBytes: int64(len(data)), SHA256: hash, BlobKey: key}
	created, isNew, e := s.store.CreateDocument(r.Context(), doc)
	if e != nil {
		s.deleteBlob(context.Background(), key)
		storeError(w, e)
		return
	}
	if !isNew {
		s.deleteBlob(context.Background(), key)
		w.Header().Set("X-Deduplicated", "true")
		respond(w, 200, created)
		return
	}
	respond(w, 201, created)
}

func (s *server) deleteDocument(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	if !validID(id) {
		problem(w, 422, "invalid_id")
		return
	}
	doc, e := s.store.DeleteDocument(r.Context(), id)
	if e != nil {
		storeError(w, e)
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), documentUploadTimeout)
	defer cancel()
	s.deleteBlob(ctx, doc.BlobKey)
	w.WriteHeader(204)
}

func (s *server) putBlob(ctx context.Context, key string, data []byte) error {
	req, e := http.NewRequestWithContext(ctx, "PUT", s.config.RuntimeURL+"/internal/v1/storage/"+key, bytes.NewReader(data))
	if e != nil {
		return ErrStorageUnavailable
	}
	req.Header.Set("Authorization", "Bearer "+s.config.InternalKey)
	req.Header.Set("Content-Type", "application/octet-stream")
	response, e := s.client.Do(req)
	if e != nil {
		return ErrStorageUnavailable
	}
	defer response.Body.Close()
	io.Copy(io.Discard, io.LimitReader(response.Body, 4096))
	if response.StatusCode != 204 {
		return ErrStorageUnavailable
	}
	return nil
}

func (s *server) deleteBlob(ctx context.Context, key string) {
	req, e := http.NewRequestWithContext(ctx, "DELETE", s.config.RuntimeURL+"/internal/v1/storage/"+key, nil)
	if e != nil {
		return
	}
	req.Header.Set("Authorization", "Bearer "+s.config.InternalKey)
	response, e := s.client.Do(req)
	if e != nil {
		log.Printf("document blob cleanup pending")
		return
	}
	defer response.Body.Close()
	io.Copy(io.Discard, io.LimitReader(response.Body, 4096))
	if response.StatusCode != 204 {
		log.Printf("document blob cleanup pending")
	}
}

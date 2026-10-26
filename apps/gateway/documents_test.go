package main

import (
	"archive/zip"
	"bytes"
	"context"
	"encoding/json"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"net/textproto"
	"strings"
	"testing"
	"time"
)

type chunkFixture struct {
	id, text                             string
	page, start, end, chunkSize, overlap int
}

type documentStore struct {
	*knowledgeStore
	docs   map[string]Document
	jobs   map[string]DocumentJob
	chunks map[string][]chunkFixture
}

func newDocumentStore() *documentStore {
	return &documentStore{knowledgeStore: newKnowledgeStore(), docs: map[string]Document{},
		jobs: map[string]DocumentJob{}, chunks: map[string][]chunkFixture{}}
}

func (s *documentStore) documentAccess(ctx context.Context, doc Document) bool {
	_, owner, e := s.kb(ctx, doc.KnowledgeBaseID)
	return e == nil && s.canAccess(ctx, owner)
}

func (s *documentStore) Documents(ctx context.Context, kbID string) ([]Document, error) {
	out := []Document{}
	for _, doc := range s.docs {
		if (kbID == "" || doc.KnowledgeBaseID == kbID) && s.documentAccess(ctx, doc) {
			out = append(out, doc)
		}
	}
	return out, nil
}

func (s *documentStore) Document(ctx context.Context, id string) (Document, error) {
	doc, ok := s.docs[id]
	if !ok || !s.documentAccess(ctx, doc) {
		return Document{}, ErrNotFound
	}
	return doc, nil
}

func (s *documentStore) DocumentByHash(ctx context.Context, kbID, hash string) (Document, error) {
	for _, doc := range s.docs {
		if doc.KnowledgeBaseID == kbID && doc.SHA256 == hash && s.documentAccess(ctx, doc) {
			return doc, nil
		}
	}
	return Document{}, ErrNotFound
}

func (s *documentStore) CreateDocument(ctx context.Context, doc Document) (Document, bool, error) {
	if e := doc.validate(); e != nil {
		return doc, false, e
	}
	if _, owner, e := s.kb(ctx, doc.KnowledgeBaseID); e != nil || !s.canAccess(ctx, owner) {
		return doc, false, ErrNotFound
	}
	for _, existing := range s.docs {
		if existing.KnowledgeBaseID == doc.KnowledgeBaseID && existing.SHA256 == doc.SHA256 {
			return existing, false, nil
		}
	}
	doc.ID = newID()
	doc.CreatedAt = time.Now().UTC()
	doc.IngestionState = "queued"
	s.docs[doc.ID] = doc
	s.jobs[doc.ID] = DocumentJob{ID: newID(), DocumentID: doc.ID, State: "queued",
		CreatedAt: doc.CreatedAt, UpdatedAt: doc.CreatedAt}
	return doc, true, nil
}

func (s *documentStore) DeleteDocument(ctx context.Context, id string) (Document, error) {
	doc, e := s.Document(ctx, id)
	if e != nil {
		return Document{}, e
	}
	delete(s.docs, id)
	delete(s.jobs, id)
	return doc, nil
}

func (s *documentStore) DocumentJob(ctx context.Context, documentID string) (DocumentJob, error) {
	if _, e := s.Document(ctx, documentID); e != nil {
		return DocumentJob{}, e
	}
	job, ok := s.jobs[documentID]
	if !ok {
		return DocumentJob{}, ErrNotFound
	}
	return job, nil
}

func (s *documentStore) CancelDocumentJob(ctx context.Context, documentID string) (DocumentJob, error) {
	job, e := s.DocumentJob(ctx, documentID)
	if e != nil {
		return DocumentJob{}, e
	}
	if job.State == "completed" || job.State == "failed" {
		return DocumentJob{}, ErrConflict
	}
	if job.State != "cancelled" {
		job.State = "cancelled"
		job.UpdatedAt = time.Now().UTC()
		s.jobs[documentID] = job
	}
	return job, nil
}

type storageCapture struct {
	puts    map[string][]byte
	deletes []string
	failPut bool
}

func (c *storageCapture) transport() roundTrip {
	return func(r *http.Request) (*http.Response, error) {
		if strings.HasPrefix(r.URL.Path, "/internal/v1/storage/") {
			key := strings.TrimPrefix(r.URL.Path, "/internal/v1/storage/")
			if r.Method == "PUT" {
				if c.failPut {
					return &http.Response{StatusCode: 503, Body: io.NopCloser(strings.NewReader(""))}, nil
				}
				data, _ := io.ReadAll(r.Body)
				c.puts[key] = data
				return &http.Response{StatusCode: 204, Body: io.NopCloser(strings.NewReader(""))}, nil
			}
			if r.Method == "DELETE" {
				c.deletes = append(c.deletes, key)
				return &http.Response{StatusCode: 204, Body: io.NopCloser(strings.NewReader(""))}, nil
			}
		}
		return &http.Response{StatusCode: 500, Body: io.NopCloser(strings.NewReader(""))}, nil
	}
}

func documentSetup(t *testing.T) (*documentStore, *server, *storageCapture) {
	t.Helper()
	store := newDocumentStore()
	s := NewServer(store, Config{Model: "test", RuntimeURL: "http://runtime", InternalKey: "internal-secret"})
	capture := &storageCapture{puts: map[string][]byte{}}
	s.client.Transport = capture.transport()
	return store, s, capture
}

func uploadBody(t *testing.T, kbID, filename, contentType string, data []byte, title string) (*bytes.Buffer, string) {
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	if e := writer.WriteField("knowledge_base_id", kbID); e != nil {
		if t != nil {
			t.Fatal(e)
		}
		return nil, ""
	}
	if title != "" {
		writer.WriteField("title", title)
	}
	header := textproto.MIMEHeader{}
	header.Set("Content-Disposition", `form-data; name="file"; filename="`+filename+`"`)
	header.Set("Content-Type", contentType)
	part, e := writer.CreatePart(header)
	if e != nil {
		if t != nil {
			t.Fatal(e)
		}
		return nil, ""
	}
	part.Write(data)
	writer.Close()
	return &body, writer.FormDataContentType()
}

func uploadRequest(s http.Handler, kbID, filename, contentType string, data []byte, key string) *httptest.ResponseRecorder {
	body, ct := uploadBody(nil, kbID, filename, contentType, data, "")
	req := httptest.NewRequest("POST", "/v1/documents", body)
	req.Header.Set("Authorization", "Bearer "+key)
	req.Header.Set("Content-Type", ct)
	w := httptest.NewRecorder()
	s.ServeHTTP(w, req)
	return w
}

func createTestKB(t *testing.T, s http.Handler, key, name string) KnowledgeBase {
	t.Helper()
	w := kbRequest(s, "POST", "/v1/knowledge-bases", `{"name":"`+name+`"}`, key, "")
	if w.Code != 201 {
		t.Fatalf("create KB: %d %s", w.Code, w.Body)
	}
	return decodeKB(t, w)
}

func decodeDocument(t *testing.T, w *httptest.ResponseRecorder) Document {
	t.Helper()
	var doc Document
	if e := json.Unmarshal(w.Body.Bytes(), &doc); e != nil {
		t.Fatalf("%v: %s", e, w.Body)
	}
	return doc
}

func TestDocumentUploadDedupListAndDelete(t *testing.T) {
	_, s, capture := documentSetup(t)
	kbA := createTestKB(t, s, "key-a", "A")
	kbB := createTestKB(t, s, "key-a", "B")
	w := uploadRequest(s, kbA.ID, "notes.txt", "text/plain", []byte("hello"), "key-a")
	if w.Code != 201 || w.Header().Get("X-Deduplicated") != "" {
		t.Fatalf("upload: %d %s", w.Code, w.Body)
	}
	doc := decodeDocument(t, w)
	if doc.IngestionState != "queued" || doc.SizeBytes != 5 || len(doc.SHA256) != 64 ||
		!strings.HasPrefix(doc.BlobKey, "documents/"+kbA.ID+"/") {
		t.Fatalf("bad doc: %s", w.Body)
	}
	if string(capture.puts[doc.BlobKey]) != "hello" {
		t.Fatal("blob not sent")
	}
	w = uploadRequest(s, kbA.ID, "notes.txt", "text/plain", []byte("hello"), "key-a")
	if w.Code != 200 || w.Header().Get("X-Deduplicated") != "true" {
		t.Fatalf("dedup: %d %s", w.Code, w.Body)
	}
	if again := decodeDocument(t, w); again.ID != doc.ID {
		t.Fatal("dedup returned a new document")
	}
	if len(capture.puts) != 1 {
		t.Fatal("dedup uploaded a second blob")
	}
	w = uploadRequest(s, kbB.ID, "notes.txt", "text/plain", []byte("hello"), "key-a")
	if w.Code != 201 {
		t.Fatalf("cross-KB dedup leaked: %d %s", w.Code, w.Body)
	}
	if len(capture.puts) != 2 {
		t.Fatal("cross-KB upload did not store a separate blob")
	}
	w = kbRequest(s, "GET", "/v1/documents?knowledge_base_id="+kbA.ID, "", "key-a", "")
	if w.Code != 200 || !strings.Contains(w.Body.String(), doc.ID) || strings.Contains(w.Body.String(), kbB.ID) {
		t.Fatalf("list: %d %s", w.Code, w.Body)
	}
	w = kbRequest(s, "GET", "/v1/documents/"+doc.ID, "", "key-a", "")
	if w.Code != 200 || !strings.Contains(w.Body.String(), doc.ID) {
		t.Fatalf("get: %d %s", w.Code, w.Body)
	}
	w = kbRequest(s, "DELETE", "/v1/documents/"+doc.ID, "", "key-a", "")
	if w.Code != 204 || len(capture.deletes) != 1 || capture.deletes[0] != doc.BlobKey {
		t.Fatalf("delete: %d %s %v", w.Code, w.Body, capture.deletes)
	}
	if w = kbRequest(s, "GET", "/v1/documents/"+doc.ID, "", "key-a", ""); w.Code != 404 {
		t.Fatalf("deleted visible: %d", w.Code)
	}
}

func TestDocumentRejectsMimeOversizeAndHostileArchives(t *testing.T) {
	_, s, _ := documentSetup(t)
	kb := createTestKB(t, s, "key-a", "A")
	pdf := []byte("%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n")
	if w := uploadRequest(s, kb.ID, "x.pdf", "text/plain", pdf, "key-a"); w.Code != 415 {
		t.Fatalf("mime mismatch: %d %s", w.Code, w.Body)
	}
	if w := uploadRequest(s, kb.ID, "x.pdf", "application/pdf", pdf, "key-a"); w.Code != 201 {
		t.Fatalf("valid pdf: %d %s", w.Code, w.Body)
	}
	docx := makeDocx(t, false)
	if w := uploadRequest(s, kb.ID, "x.docx",
		"application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx, "key-a"); w.Code != 201 {
		t.Fatalf("valid docx: %d %s", w.Code, w.Body)
	}
	hostile := makeDocx(t, true)
	if w := uploadRequest(s, kb.ID, "x.docx",
		"application/vnd.openxmlformats-officedocument.wordprocessingml.document", hostile, "key-a"); w.Code != 415 {
		t.Fatalf("hostile docx: %d %s", w.Code, w.Body)
	}
	if w := uploadRequest(s, kb.ID, "x.txt", "text/plain", bytes.Repeat([]byte("x"), maxDocumentBytes+1), "key-a"); w.Code != 413 {
		t.Fatalf("oversize: %d %s", w.Code, w.Body)
	}
}

func TestDocumentOwnershipAndScopes(t *testing.T) {
	_, s, _ := documentSetup(t)
	kb := createTestKB(t, s, "key-a", "A")
	w := uploadRequest(s, kb.ID, "notes.txt", "text/plain", []byte("hello"), "key-a")
	doc := decodeDocument(t, w)
	if w = kbRequest(s, "GET", "/v1/documents/"+doc.ID, "", "key-b", ""); w.Code != 404 {
		t.Fatalf("foreign get: %d %s", w.Code, w.Body)
	}
	if w = uploadRequest(s, kb.ID, "other.txt", "text/plain", []byte("other"), "key-b"); w.Code != 404 {
		t.Fatalf("foreign upload: %d %s", w.Code, w.Body)
	}
	if w = uploadRequest(s, kb.ID, "read.txt", "text/plain", []byte("read"), "key-read"); w.Code != 403 {
		t.Fatalf("read-only upload: %d %s", w.Code, w.Body)
	}
	if w = kbRequest(s, "GET", "/v1/documents", "", "key-read", ""); w.Code != 200 {
		t.Fatalf("read list: %d %s", w.Code, w.Body)
	}
}

func TestDocumentStorageFailureDoesNotCreateMetadata(t *testing.T) {
	store, s, capture := documentSetup(t)
	kb := createTestKB(t, s, "key-a", "A")
	capture.failPut = true
	if w := uploadRequest(s, kb.ID, "notes.txt", "text/plain", []byte("hello"), "key-a"); w.Code != 503 {
		t.Fatalf("storage failure: %d %s", w.Code, w.Body)
	}
	if len(store.docs) != 0 {
		t.Fatal("metadata created without blob")
	}
}

func makeDocx(t *testing.T, hostile bool) []byte {
	t.Helper()
	var buffer bytes.Buffer
	writer := zip.NewWriter(&buffer)
	files := map[string]string{
		"[Content_Types].xml": `<?xml version="1.0"?><Types/>`,
		"word/document.xml":   `<w:document/>`,
	}
	if hostile {
		files["word/vbaProject.bin"] = "macro"
	}
	for name, content := range files {
		file, e := writer.Create(name)
		if e != nil {
			t.Fatal(e)
		}
		file.Write([]byte(content))
	}
	if e := writer.Close(); e != nil {
		t.Fatal(e)
	}
	return buffer.Bytes()
}

func (s *documentStore) KnowledgeBaseExport(ctx context.Context, id string) (KnowledgeBaseExport, error) {
	export, e := s.knowledgeStore.KnowledgeBaseExport(ctx, id)
	if e != nil {
		return KnowledgeBaseExport{}, e
	}
	export.Documents, _ = s.Documents(ctx, id)
	for i := range export.Documents {
		export.Documents[i].BlobKey = ""
	}
	export.Chunks = []ExportChunk{}
	for _, doc := range export.Documents {
		for _, chunk := range s.chunks[doc.ID] {
			export.Chunks = append(export.Chunks, ExportChunk{ChunkID: chunk.id, DocumentID: doc.ID,
				DocumentHash: doc.SHA256, DocumentVersion: 1, Page: chunk.page, Start: chunk.start,
				End: chunk.end, Text: chunk.text, ChunkSize: chunk.chunkSize, Overlap: chunk.overlap})
		}
	}
	return export, nil
}

package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

type knowledgeStore struct {
	memoryStore
	kbs        map[string]KnowledgeBase
	kbOwners   map[string]string
	kbVersions map[string][]KnowledgeBaseVersion
	assistants map[string]Assistant
	asstOwners map[string]string
	asstVers   map[string][]Assistant
}

func newKnowledgeStore() *knowledgeStore {
	return &knowledgeStore{
		kbs: map[string]KnowledgeBase{}, kbOwners: map[string]string{},
		kbVersions: map[string][]KnowledgeBaseVersion{},
		assistants: map[string]Assistant{}, asstOwners: map[string]string{},
		asstVers: map[string][]Assistant{},
	}
}

func digestKey(key string) string {
	sum := sha256.Sum256([]byte(key))
	return hex.EncodeToString(sum[:])
}

func (s *knowledgeStore) Authenticate(_ context.Context, digest string) (Principal, error) {
	for key, id := range map[string]string{"key-a": "user-a", "key-b": "user-b", "key-read": "user-read"} {
		if digest == digestKey(key) {
			if key == "key-read" {
				return Principal{ID: id, Role: "reader", Scopes: []string{"agent-runs:read", "documents:read", "knowledge-bases:read"}}, nil
			}
			return Principal{ID: id, Role: "operator", Scopes: []string{
				"agent-runs:read", "agent-runs:write",
				"documents:read", "documents:write",
				"knowledge-bases:read", "knowledge-bases:write",
				"assistants:read", "assistants:write",
			}}, nil
		}
	}
	return Principal{}, ErrUnauthorized
}

func (s *knowledgeStore) canAccess(ctx context.Context, owner string) bool {
	p := currentPrincipal(ctx)
	return p.isAdmin() || p.ID == owner
}

func (s *knowledgeStore) kb(ctx context.Context, id string) (KnowledgeBase, string, error) {
	kb, ok := s.kbs[id]
	if !ok || !s.canAccess(ctx, s.kbOwners[id]) {
		return KnowledgeBase{}, "", ErrNotFound
	}
	return kb, s.kbOwners[id], nil
}

func (s *knowledgeStore) KnowledgeBases(ctx context.Context) ([]KnowledgeBase, error) {
	out := []KnowledgeBase{}
	for id, kb := range s.kbs {
		if s.canAccess(ctx, s.kbOwners[id]) {
			out = append(out, kb)
		}
	}
	return out, nil
}

func (s *knowledgeStore) KnowledgeBase(ctx context.Context, id string) (KnowledgeBase, error) {
	kb, _, e := s.kb(ctx, id)
	return kb, e
}

func (s *knowledgeStore) KnowledgeBaseVersions(ctx context.Context, id string) ([]KnowledgeBaseVersion, error) {
	if _, _, e := s.kb(ctx, id); e != nil {
		return nil, e
	}
	return append([]KnowledgeBaseVersion{}, s.kbVersions[id]...), nil
}

func (s *knowledgeStore) CreateKnowledgeBase(ctx context.Context, name, description string, config KnowledgeBaseConfig, embedding *KnowledgeBaseEmbedding) (KnowledgeBase, error) {
	kb := KnowledgeBase{ID: newID(), Name: name, Description: description, Revision: 1,
		ActiveVersion: 1, CreatedAt: time.Now().UTC(), UpdatedAt: time.Now().UTC()}
	s.kbs[kb.ID] = kb
	s.kbOwners[kb.ID] = currentPrincipal(ctx).ID
	version := KnowledgeBaseVersion{Version: 1, State: knowledgeBaseActive, Config: config,
		Embedding: embedding, CreatedAt: kb.CreatedAt}
	if embedding != nil {
		version.CollectionName = embedding.collectionName(kb.ID)
	}
	s.kbVersions[kb.ID] = []KnowledgeBaseVersion{version}
	return kb, nil
}

func (s *knowledgeStore) UpdateKnowledgeBase(ctx context.Context, id string, expected int, candidate KnowledgeBase) (KnowledgeBase, error) {
	kb, owner, e := s.kb(ctx, id)
	if e != nil {
		return KnowledgeBase{}, e
	}
	if kb.Revision != expected {
		return KnowledgeBase{}, ErrPreconditionFailed
	}
	kb.Name, kb.Description = candidate.Name, candidate.Description
	kb.Revision++
	kb.UpdatedAt = time.Now().UTC()
	s.kbs[id] = kb
	s.kbOwners[id] = owner
	return kb, nil
}

func (s *knowledgeStore) DeleteKnowledgeBase(ctx context.Context, id string, expected int) error {
	kb, _, e := s.kb(ctx, id)
	if e != nil {
		return e
	}
	if kb.Revision != expected {
		return ErrPreconditionFailed
	}
	for _, a := range s.assistants {
		if a.Version > 0 && containsString(a.KnowledgeBaseIDs, id) && s.asstOwners[a.ID] == s.kbOwners[id] {
			return ErrConflict
		}
	}
	delete(s.kbs, id)
	delete(s.kbOwners, id)
	delete(s.kbVersions, id)
	return nil
}

func (s *knowledgeStore) CreateKnowledgeBaseVersion(ctx context.Context, id string, expected int, config KnowledgeBaseConfig, embedding *KnowledgeBaseEmbedding) (KnowledgeBase, KnowledgeBaseVersion, error) {
	kb, owner, e := s.kb(ctx, id)
	if e != nil {
		return KnowledgeBase{}, KnowledgeBaseVersion{}, e
	}
	if kb.Revision != expected {
		return KnowledgeBase{}, KnowledgeBaseVersion{}, ErrPreconditionFailed
	}
	for _, v := range s.kbVersions[id] {
		if v.State == knowledgeBaseReindexing || v.State == knowledgeBaseBuilding {
			return KnowledgeBase{}, KnowledgeBaseVersion{}, ErrConflict
		}
	}
	if embedding == nil {
		for _, v := range s.kbVersions[id] {
			if v.Version == kb.ActiveVersion {
				embedding = v.Embedding
			}
		}
	}
	next := 1
	for _, v := range s.kbVersions[id] {
		if v.Version >= next {
			next = v.Version + 1
		}
	}
	version := KnowledgeBaseVersion{Version: next, State: knowledgeBaseReindexing, Config: config,
		Embedding: embedding, CreatedAt: time.Now().UTC()}
	if embedding != nil {
		version.CollectionName = embedding.collectionName(id)
	}
	s.kbVersions[id] = append(s.kbVersions[id], version)
	kb.Revision++
	kb.UpdatedAt = time.Now().UTC()
	s.kbs[id] = kb
	s.kbOwners[id] = owner
	return kb, version, nil
}

func (s *knowledgeStore) validateKBs(ctx context.Context, ids []string) error {
	for _, id := range ids {
		if !validID(id) {
			return ErrInvalidConfig
		}
		if _, _, e := s.kb(ctx, id); e != nil {
			return ErrInvalidConfig
		}
	}
	return nil
}

func (s *knowledgeStore) CreateAssistant(ctx context.Context, a Assistant) (Assistant, error) {
	if e := a.validate(); e != nil {
		return a, e
	}
	if e := s.validateKBs(ctx, a.KnowledgeBaseIDs); e != nil {
		return a, e
	}
	a.ID, a.Version = newID(), 1
	s.assistants[a.ID] = a
	s.asstOwners[a.ID] = currentPrincipal(ctx).ID
	s.asstVers[a.ID] = []Assistant{a}
	return a, nil
}

func (s *knowledgeStore) Assistant(ctx context.Context, id string) (Assistant, error) {
	a, ok := s.assistants[id]
	if !ok || !s.canAccess(ctx, s.asstOwners[id]) {
		return Assistant{}, ErrNotFound
	}
	return a, nil
}

func (s *knowledgeStore) Assistants(ctx context.Context) ([]Assistant, error) {
	out := []Assistant{}
	for id, a := range s.assistants {
		if s.canAccess(ctx, s.asstOwners[id]) {
			out = append(out, a)
		}
	}
	return out, nil
}

func (s *knowledgeStore) AssistantVersions(ctx context.Context, id string) ([]Assistant, error) {
	if _, e := s.Assistant(ctx, id); e != nil {
		return nil, e
	}
	return append([]Assistant{}, s.asstVers[id]...), nil
}

func (s *knowledgeStore) UpdateAssistant(ctx context.Context, id string, expected int, patch json.RawMessage) (Assistant, error) {
	current, e := s.Assistant(ctx, id)
	if e != nil {
		return Assistant{}, e
	}
	if current.Version != expected {
		return Assistant{}, ErrPreconditionFailed
	}
	next, e := applyAssistantPatch(current, patch)
	if e != nil {
		return Assistant{}, e
	}
	if e = s.validateKBs(ctx, next.KnowledgeBaseIDs); e != nil {
		return Assistant{}, e
	}
	next.Version++
	s.assistants[id] = next
	s.asstVers[id] = append(s.asstVers[id], next)
	return next, nil
}

func containsString(values []string, want string) bool {
	for _, value := range values {
		if value == want {
			return true
		}
	}
	return false
}

func knowledgeSetup(t *testing.T) (*knowledgeStore, *server) {
	t.Helper()
	store := newKnowledgeStore()
	return store, NewServer(store, Config{Model: "test", RuntimeURL: "http://runtime", InternalKey: "internal-secret"})
}

func kbRequest(s http.Handler, method, path, body, key, etag string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+key)
	req.Header.Set("Content-Type", "application/json")
	if etag != "" {
		req.Header.Set("If-Match", etag)
	}
	w := httptest.NewRecorder()
	s.ServeHTTP(w, req)
	return w
}

func decodeKB(t *testing.T, w *httptest.ResponseRecorder) KnowledgeBase {
	t.Helper()
	var kb KnowledgeBase
	if e := json.Unmarshal(w.Body.Bytes(), &kb); e != nil {
		t.Fatalf("%v: %s", e, w.Body)
	}
	return kb
}

func TestKnowledgeBaseCRUDVersionsAndAccess(t *testing.T) {
	_, s := knowledgeSetup(t)
	w := kbRequest(s, "POST", "/v1/knowledge-bases", `{"name":"Docs","description":"Corpus"}`, "key-a", "")
	if w.Code != 201 || w.Header().Get("ETag") != `"1"` {
		t.Fatalf("create: %d %s", w.Code, w.Body)
	}
	kb := decodeKB(t, w)
	if kb.ID == "" || kb.Revision != 1 || kb.ActiveVersion != 1 || kb.Name != "Docs" {
		t.Fatalf("bad body: %s", w.Body)
	}
	if w := kbRequest(s, "GET", "/v1/knowledge-bases", "", "key-a", ""); w.Code != 200 ||
		!strings.Contains(w.Body.String(), kb.ID) {
		t.Fatalf("list: %d %s", w.Code, w.Body)
	}
	if w := kbRequest(s, "GET", "/v1/knowledge-bases/"+kb.ID, "", "key-a", ""); w.Code != 200 ||
		w.Header().Get("ETag") != `"1"` {
		t.Fatalf("get: %d %s", w.Code, w.Body)
	}
	if w := kbRequest(s, "PATCH", "/v1/knowledge-bases/"+kb.ID, `{"name":"Docs 2"}`, "key-a", ""); w.Code != 428 {
		t.Fatalf("missing if-match: %d %s", w.Code, w.Body)
	}
	if w := kbRequest(s, "PATCH", "/v1/knowledge-bases/"+kb.ID, `{"name":"Docs 2"}`, "key-a", `"1"`); w.Code != 200 ||
		w.Header().Get("ETag") != `"2"` {
		t.Fatalf("patch: %d %s", w.Code, w.Body)
	}
	if w := kbRequest(s, "PATCH", "/v1/knowledge-bases/"+kb.ID, `{"name":"Stale"}`, "key-a", `"1"`); w.Code != 412 {
		t.Fatalf("stale patch: %d %s", w.Code, w.Body)
	}
	for _, body := range []string{`{"config":{"chunk_size":10}}`, `{"unknown":true}`, `{"name":null}`, `{}`} {
		if w := kbRequest(s, "PATCH", "/v1/knowledge-bases/"+kb.ID, body, "key-a", `"2"`); w.Code != 422 {
			t.Fatalf("invalid patch %s: %d %s", body, w.Code, w.Body)
		}
	}
	if w := kbRequest(s, "GET", "/v1/knowledge-bases/"+kb.ID+"/versions", "", "key-a", ""); w.Code != 200 ||
		!strings.Contains(w.Body.String(), `"active"`) || !strings.Contains(w.Body.String(), `"chunk_size":1000`) {
		t.Fatalf("versions: %d %s", w.Code, w.Body)
	}
	if w := kbRequest(s, "POST", "/v1/knowledge-bases/"+kb.ID+"/versions", `{"config":{"chunk_size":500,"chunk_overlap":50}}`, "key-a", ""); w.Code != 428 {
		t.Fatalf("version missing if-match: %d %s", w.Code, w.Body)
	}
	if w := kbRequest(s, "POST", "/v1/knowledge-bases/"+kb.ID+"/versions", `{}`, "key-a", `"2"`); w.Code != 422 {
		t.Fatalf("version without config: %d %s", w.Code, w.Body)
	}
	if w := kbRequest(s, "POST", "/v1/knowledge-bases/"+kb.ID+"/versions", `{"config":{"chunk_size":500,"chunk_overlap":50}}`, "key-a", `"2"`); w.Code != 201 ||
		w.Header().Get("ETag") != `"3"` || !strings.Contains(w.Body.String(), `"reindexing"`) {
		t.Fatalf("version: %d %s", w.Code, w.Body)
	}
	if w := kbRequest(s, "GET", "/v1/knowledge-bases/"+kb.ID, "", "key-a", ""); w.Code != 200 ||
		!strings.Contains(w.Body.String(), `"active_version":1`) || !strings.Contains(w.Body.String(), `"revision":3`) {
		t.Fatalf("active version changed: %d %s", w.Code, w.Body)
	}
	if w := kbRequest(s, "POST", "/v1/knowledge-bases/"+kb.ID+"/versions", `{"config":{"chunk_size":500,"chunk_overlap":50}}`, "key-a", `"3"`); w.Code != 409 {
		t.Fatalf("second reindexing: %d %s", w.Code, w.Body)
	}
	if w := kbRequest(s, "POST", "/v1/knowledge-bases/"+kb.ID+"/versions", `{"config":{"chunk_size":100,"chunk_overlap":100}}`, "key-a", `"3"`); w.Code != 422 {
		t.Fatalf("invalid config: %d %s", w.Code, w.Body)
	}
	// Cross-principal access must be indistinguishable from an unknown KB.
	if w := kbRequest(s, "GET", "/v1/knowledge-bases", "", "key-b", ""); w.Code != 200 || strings.Contains(w.Body.String(), kb.ID) {
		t.Fatalf("cross list: %d %s", w.Code, w.Body)
	}
	for _, method := range []string{"GET", "PATCH", "DELETE"} {
		body := ""
		if method == "PATCH" {
			body = `{"name":"Owned"}`
		}
		if w := kbRequest(s, method, "/v1/knowledge-bases/"+kb.ID, body, "key-b", `"2"`); w.Code != 404 {
			t.Fatalf("cross %s: %d %s", method, w.Code, w.Body)
		}
	}
}

func TestAssistantKnowledgeBaseAssociationsAndDeleteGuard(t *testing.T) {
	_, s := knowledgeSetup(t)
	w := kbRequest(s, "POST", "/v1/knowledge-bases", `{"name":"A"}`, "key-a", "")
	kbA := decodeKB(t, w)
	w = kbRequest(s, "POST", "/v1/knowledge-bases", `{"name":"B"}`, "key-b", "")
	kbB := decodeKB(t, w)

	w = kbRequest(s, "POST", "/v1/assistants", `{"name":"A","model":"test","system_prompt":"","knowledge_base_ids":["`+kbA.ID+`"]}`, "key-a", "")
	if w.Code != 201 || !strings.Contains(w.Body.String(), kbA.ID) {
		t.Fatalf("associate own: %d %s", w.Code, w.Body)
	}
	var assistant Assistant
	json.Unmarshal(w.Body.Bytes(), &assistant)
	if w = kbRequest(s, "POST", "/v1/assistants", `{"name":"B","model":"test","system_prompt":"","knowledge_base_ids":["`+kbB.ID+`"]}`, "key-a", ""); w.Code != 422 {
		t.Fatalf("associate foreign: %d %s", w.Code, w.Body)
	}
	if w = kbRequest(s, "POST", "/v1/assistants", `{"name":"B","model":"test","system_prompt":"","knowledge_base_ids":["`+kbA.ID+`"]}`, "key-b", ""); w.Code != 422 {
		t.Fatalf("foreign associate: %d %s", w.Code, w.Body)
	}
	if w = kbRequest(s, "DELETE", "/v1/knowledge-bases/"+kbA.ID, "", "key-a", `"1"`); w.Code != 409 {
		t.Fatalf("delete referenced: %d %s", w.Code, w.Body)
	}
	if w = kbRequest(s, "PATCH", "/v1/assistants/"+assistant.ID, `{"knowledge_base_ids":[]}`, "key-a", `"1"`); w.Code != 200 {
		t.Fatalf("detach: %d %s", w.Code, w.Body)
	}
	if w = kbRequest(s, "DELETE", "/v1/knowledge-bases/"+kbA.ID, "", "key-a", `"1"`); w.Code != 204 {
		t.Fatalf("delete detached: %d %s", w.Code, w.Body)
	}
	if w = kbRequest(s, "GET", "/v1/knowledge-bases/"+kbA.ID, "", "key-a", ""); w.Code != 404 {
		t.Fatalf("deleted kb visible: %d %s", w.Code, w.Body)
	}
}

func TestKnowledgeBaseConfigAndMetadataValidation(t *testing.T) {
	if defaultKnowledgeBaseConfig().validate() != nil {
		t.Fatal("default config invalid")
	}
	for _, c := range []KnowledgeBaseConfig{{ChunkSize: 99}, {ChunkSize: 1001, ChunkOverlap: 1001}, {ChunkOverlap: -1}} {
		if c.validate() == nil {
			t.Fatalf("accepted invalid config: %+v", c)
		}
	}
	for _, kb := range []KnowledgeBase{{Name: ""}, {Name: strings.Repeat("x", 201)}, {Name: "x", Revision: 0}, {Name: "x", ActiveVersion: 0}} {
		if kb.validate() == nil {
			t.Fatalf("accepted invalid KB: %+v", kb)
		}
	}
}

func (s *knowledgeStore) KnowledgeBaseExport(ctx context.Context, id string) (KnowledgeBaseExport, error) {
	kb, e := s.KnowledgeBase(ctx, id)
	if e != nil {
		return KnowledgeBaseExport{}, e
	}
	versions, e := s.KnowledgeBaseVersions(ctx, id)
	if e != nil {
		return KnowledgeBaseExport{}, e
	}
	return KnowledgeBaseExport{KnowledgeBase: kb, Versions: versions, Documents: []Document{},
		Chunks: []ExportChunk{}, ExportedAt: time.Now().UTC()}, nil
}

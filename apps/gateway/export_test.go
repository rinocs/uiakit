package main

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestKnowledgeBaseEmbeddingVersionAndExport(t *testing.T) {
	store, s, _ := documentSetup(t)
	w := kbRequest(s, "POST", "/v1/knowledge-bases",
		`{"name":"Indexed","embedding":{"provider":"ollama","model":"nomic-embed-text","version":"v1","dimension":3}}`,
		"key-a", "")
	if w.Code != 201 {
		t.Fatalf("create: %d %s", w.Code, w.Body)
	}
	kb := decodeKB(t, w)
	w = uploadRequest(s, kb.ID, "notes.txt", "text/plain", []byte("hello world"), "key-a")
	if w.Code != 201 {
		t.Fatalf("upload: %d %s", w.Code, w.Body)
	}
	doc := decodeDocument(t, w)
	store.chunks[doc.ID] = []chunkFixture{{id: strings.Repeat("a", 64), text: "hello", page: 1,
		start: 0, end: 5, chunkSize: 1000, overlap: 200}}
	w = kbRequest(s, "GET", "/v1/knowledge-bases/"+kb.ID+"/export", "", "key-a", "")
	if w.Code != 200 {
		t.Fatalf("export: %d %s", w.Code, w.Body)
	}
	var export KnowledgeBaseExport
	if e := json.Unmarshal(w.Body.Bytes(), &export); e != nil {
		t.Fatal(e)
	}
	if export.KnowledgeBase.ID != kb.ID || len(export.Versions) != 1 ||
		export.Versions[0].Embedding == nil || export.Versions[0].CollectionName == "" ||
		len(export.Documents) != 1 || len(export.Chunks) != 1 || export.Chunks[0].Text != "hello" {
		t.Fatalf("bad export: %s", w.Body)
	}
	if strings.Contains(w.Body.String(), `"blob_key"`) {
		t.Fatalf("export leaked blob key: %s", w.Body)
	}
	if w = kbRequest(s, "GET", "/v1/knowledge-bases/"+kb.ID+"/export", "", "key-b", ""); w.Code != 404 {
		t.Fatalf("foreign export: %d", w.Code)
	}
	w = kbRequest(s, "POST", "/v1/knowledge-bases/"+kb.ID+"/versions",
		`{"config":{"chunk_size":500,"chunk_overlap":50},"embedding":{"provider":"ollama","model":"nomic-embed-text","version":"v2","dimension":3}}`,
		"key-a", `"1"`)
	if w.Code != 201 || !strings.Contains(w.Body.String(), `"state":"reindexing"`) ||
		!strings.Contains(w.Body.String(), `"collection_name"`) {
		t.Fatalf("version: %d %s", w.Code, w.Body)
	}
	w = kbRequest(s, "POST", "/v1/knowledge-bases",
		`{"name":"Copy","embedding":{"provider":"ollama","model":"nomic-embed-text","version":"v1","dimension":3}}`,
		"key-a", "")
	copyKB := decodeKB(t, w)
	w = kbRequest(s, "POST", "/v1/knowledge-bases/"+copyKB.ID+"/versions",
		`{"config":{"chunk_size":600,"chunk_overlap":60}}`, "key-a", `"1"`)
	if w.Code != 201 || !strings.Contains(w.Body.String(), `"version":"v1"`) {
		t.Fatalf("embedding copy: %d %s", w.Code, w.Body)
	}
	if w = kbRequest(s, "POST", "/v1/knowledge-bases", `{"name":"Bad","embedding":{"provider":"ollama","model":"x","version":"v","dimension":0}}`, "key-a", ""); w.Code != 422 {
		t.Fatalf("invalid embedding: %d %s", w.Code, w.Body)
	}
}

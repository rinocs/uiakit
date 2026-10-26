package main

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestDocumentJobStatusAndCancellation(t *testing.T) {
	store, s, _ := documentSetup(t)
	kb := createTestKB(t, s, "key-a", "A")
	w := uploadRequest(s, kb.ID, "notes.txt", "text/plain", []byte("hello"), "key-a")
	if w.Code != 201 {
		t.Fatalf("upload: %d %s", w.Code, w.Body)
	}
	doc := decodeDocument(t, w)
	path := "/v1/documents/" + doc.ID + "/job"
	if w = kbRequest(s, "GET", path, "", "key-a", ""); w.Code != 200 ||
		!strings.Contains(w.Body.String(), `"state":"queued"`) {
		t.Fatalf("job: %d %s", w.Code, w.Body)
	}
	if w = kbRequest(s, "GET", path, "", "key-b", ""); w.Code != 404 {
		t.Fatalf("foreign job: %d %s", w.Code, w.Body)
	}
	if w = kbRequest(s, "POST", path+"/cancel", "", "key-a", ""); w.Code != 200 {
		t.Fatalf("cancel: %d %s", w.Code, w.Body)
	}
	var job DocumentJob
	json.Unmarshal(w.Body.Bytes(), &job)
	if job.State != "cancelled" {
		t.Fatalf("state: %s", w.Body)
	}
	if w = kbRequest(s, "POST", path+"/cancel", "", "key-a", ""); w.Code != 200 {
		t.Fatalf("cancel idempotent: %d %s", w.Code, w.Body)
	}
	store.jobs[doc.ID] = DocumentJob{ID: job.ID, DocumentID: doc.ID, State: "completed"}
	if w = kbRequest(s, "POST", path+"/cancel", "", "key-a", ""); w.Code != 409 {
		t.Fatalf("cancel terminal: %d %s", w.Code, w.Body)
	}
}

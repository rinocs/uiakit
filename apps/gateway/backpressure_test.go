package main

import (
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"sync"
	"testing"
	"time"
)

type deadlineWriter struct {
	mu         sync.Mutex
	deadline   time.Time
	header     http.Header
	statusCode int
}

func (w *deadlineWriter) Header() http.Header {
	if w.header == nil {
		w.header = http.Header{}
	}
	return w.header
}

func (w *deadlineWriter) WriteHeader(status int) { w.statusCode = status }

func (w *deadlineWriter) Write([]byte) (int, error) {
	w.mu.Lock()
	deadline := w.deadline
	w.mu.Unlock()
	if deadline.IsZero() {
		return 0, errors.New("write deadline not set")
	}
	if wait := time.Until(deadline); wait > 0 {
		time.Sleep(wait)
	}
	return 0, os.ErrDeadlineExceeded
}

func (w *deadlineWriter) SetWriteDeadline(deadline time.Time) error {
	w.mu.Lock()
	w.deadline = deadline
	w.mu.Unlock()
	return nil
}

func (w *deadlineWriter) Flush() {}

func TestSlowClientWriteDeadlineBoundsHandler(t *testing.T) {
	writer := &deadlineWriter{}
	event := Event{
		ID:            newID(),
		Type:          "response.completed",
		Version:       1,
		Timestamp:     time.Now().UTC(),
		RunID:         newID(),
		CorrelationID: newID(),
		Payload:       json.RawMessage(`{"text":"bounded"}`),
	}
	started := time.Now()
	err := writeEventWithTimeout(writer, event, 50*time.Millisecond)
	if err == nil {
		t.Fatal("slow client write must fail instead of pinning the handler")
	}
	if elapsed := time.Since(started); elapsed > time.Second {
		t.Fatalf("write deadline not enforced: %s", elapsed)
	}
	writer.mu.Lock()
	defer writer.mu.Unlock()
	if writer.deadline.IsZero() {
		t.Fatal("SSE writes must set a deadline")
	}
}

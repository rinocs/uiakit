package uai

import (
	"strings"
	"testing"
)

func TestSSEDecoderFragmentedFrame(t *testing.T) {
	decoder := &SSEDecoder{}
	frame := []byte("id: e1\nevent: response.delta\ndata: {\"text\":\"hello\"}\n\n")
	if got := decoder.Push(frame[:19]); len(got) != 0 {
		t.Fatalf("first chunk dispatched %d events", len(got))
	}
	got := decoder.Push(frame[19:])
	if len(got) != 1 {
		t.Fatalf("got %d events, want 1", len(got))
	}
	if got[0].ID != "e1" || got[0].Event != "response.delta" {
		t.Fatalf("unexpected event: %#v", got[0])
	}
	if got[0].Data != `{"text":"hello"}` {
		t.Fatalf("unexpected data: %q", got[0].Data)
	}
}

func TestSSEDecoderPreservesUnicodeSplitAcrossChunks(t *testing.T) {
	decoder := &SSEDecoder{}
	frame := []byte("data: {\"text\":\"caffè 😀\"}\n\n")
	cut := strings.Index(string(frame), "😀") + 2
	if got := decoder.Push(frame[:cut]); len(got) != 0 {
		t.Fatalf("first chunk dispatched %d events", len(got))
	}
	got := decoder.Push(frame[cut:])
	if len(got) != 1 {
		t.Fatalf("got %d events, want 1", len(got))
	}
	if got[0].Data != `{"text":"caffè 😀"}` {
		t.Fatalf("unexpected data: %q", got[0].Data)
	}
}

func TestSSEDecoderSupportsCRLFCommentsAndMultilineData(t *testing.T) {
	decoder := &SSEDecoder{}
	got := decoder.Push([]byte(": keepalive\r\nevent: response.delta\r\ndata: first\r\ndata: second\r\n\r\n"))
	if len(got) != 1 {
		t.Fatalf("got %d events, want 1", len(got))
	}
	if got[0].Event != "response.delta" || got[0].Data != "first\nsecond" {
		t.Fatalf("unexpected event: %#v", got[0])
	}
}

func TestSSEDecoderDoesNotDispatchUnfinishedFrameAtEOF(t *testing.T) {
	decoder := &SSEDecoder{}
	if got := decoder.Push([]byte("data: unfinished")); len(got) != 0 {
		t.Fatalf("got %d events, want 0", len(got))
	}
	if got := decoder.End(); len(got) != 0 {
		t.Fatalf("end dispatched %d events, want 0", len(got))
	}
}

package uai

import (
	"bytes"
	"strings"
)

// SSEEvent is one dispatched Server-Sent Event frame.
type SSEEvent struct {
	ID    string
	Event string
	Data  string
}

// SSEDecoder accepts arbitrary byte chunks and dispatches complete SSE frames.
// UTF-8 code points may be split across chunks because parsing is byte-oriented
// and only complete lines are interpreted.
type SSEDecoder struct {
	buffer      []byte
	data        []string
	event       string
	id          string
	lastEventID string
}

func (d *SSEDecoder) Push(chunk []byte) []SSEEvent {
	d.buffer = append(d.buffer, chunk...)
	return d.drain(false)
}

func (d *SSEDecoder) End() []SSEEvent {
	events := d.drain(true)
	d.data = nil
	d.event = ""
	d.id = ""
	return events
}

func (d *SSEDecoder) drain(atEnd bool) []SSEEvent {
	var events []SSEEvent
	for {
		index := bytes.IndexAny(d.buffer, "\r\n")
		if index < 0 {
			break
		}
		character := d.buffer[index]
		if character == '\r' && index == len(d.buffer)-1 && !atEnd {
			break
		}
		next := index + 1
		if character == '\r' && next < len(d.buffer) && d.buffer[next] == '\n' {
			next++
		}
		line := string(d.buffer[:index])
		d.buffer = d.buffer[next:]
		if event, ok := d.consumeLine(line); ok {
			events = append(events, event)
		}
	}
	if atEnd && len(d.buffer) > 0 {
		line := string(d.buffer)
		d.buffer = nil
		if event, ok := d.consumeLine(line); ok {
			events = append(events, event)
		}
	}
	return events
}

func (d *SSEDecoder) consumeLine(line string) (SSEEvent, bool) {
	if line == "" {
		data := strings.Join(d.data, "\n")
		event := d.event
		id := d.id
		if id == "" {
			id = d.lastEventID
		}
		d.data = nil
		d.event = ""
		d.id = ""
		if data == "" {
			return SSEEvent{}, false
		}
		return SSEEvent{ID: id, Event: event, Data: data}, true
	}
	if strings.HasPrefix(line, ":") {
		return SSEEvent{}, false
	}
	field, value, found := strings.Cut(line, ":")
	if !found {
		value = ""
	}
	value = strings.TrimPrefix(value, " ")
	switch field {
	case "data":
		d.data = append(d.data, value)
	case "event":
		d.event = value
	case "id":
		if !strings.ContainsRune(value, '\x00') {
			d.id = value
			d.lastEventID = value
		}
	case "retry":
	}
	return SSEEvent{}, false
}

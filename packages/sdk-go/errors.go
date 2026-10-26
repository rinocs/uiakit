package uai

import "fmt"

type ValidationError struct {
	Message string
}

func (e *ValidationError) Error() string { return e.Message }

type APIError struct {
	Status  int
	Code    string
	Body    string
	Message string
}

func (e *APIError) Error() string {
	if e.Message != "" {
		return e.Message
	}
	return fmt.Sprintf("gateway request failed with status %d (%s)", e.Status, e.Code)
}

type AbortError struct {
	Err error
}

func (e *AbortError) Error() string { return "operation aborted" }
func (e *AbortError) Unwrap() error { return e.Err }

type TimeoutError struct {
	Err error
}

func (e *TimeoutError) Error() string { return "operation timed out" }
func (e *TimeoutError) Unwrap() error { return e.Err }

type NetworkError struct {
	Err error
}

func (e *NetworkError) Error() string { return "network request failed" }
func (e *NetworkError) Unwrap() error { return e.Err }

type StreamIncompleteError struct {
	RunID string
}

func (e *StreamIncompleteError) Error() string {
	return "event stream ended without a terminal event"
}

type StreamProtocolError struct {
	Message string
	Err     error
}

func (e *StreamProtocolError) Error() string { return e.Message }
func (e *StreamProtocolError) Unwrap() error { return e.Err }

type ResponseError struct {
	Message string
	Err     error
}

func (e *ResponseError) Error() string { return e.Message }
func (e *ResponseError) Unwrap() error { return e.Err }

type AgentFailedError struct {
	Event RuntimeEvent
	Code  string
}

func (e *AgentFailedError) Error() string {
	return fmt.Sprintf("agent run failed (%s)", e.Code)
}

type AgentCancelledError struct {
	Event RuntimeEvent
	Code  string
}

func (e *AgentCancelledError) Error() string {
	return fmt.Sprintf("agent run was cancelled (%s)", e.Code)
}

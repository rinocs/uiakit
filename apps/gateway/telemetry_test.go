package main

import (
	"context"
	"net/http"
	"testing"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/propagation"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
	"go.opentelemetry.io/otel/trace"
)

func traceID(ctx context.Context) string {
	span := trace.SpanFromContext(ctx)
	if !span.SpanContext().IsValid() {
		return ""
	}
	return span.SpanContext().TraceID().String()
}

func TestTelemetryDropsSensitiveAndHighCardinalityAttributes(t *testing.T) {
	exporter := tracetest.NewInMemoryExporter()
	provider := sdktrace.NewTracerProvider(sdktrace.WithSyncer(exporter))
	telemetry := &Telemetry{enabled: true, tracer: provider.Tracer("test")}
	ctx, span := telemetry.Start(context.Background(), "run", attribute.String("run_id", "run-1"))
	span.SetAttributes(telemetryAttributes(
		attribute.String("prompt", "do not export"),
		attribute.String("authorization", "Bearer secret"),
		attribute.String("model", "test-model"),
	)...)
	span.End()
	_ = ctx
	spans := exporter.GetSpans()
	if len(spans) != 1 {
		t.Fatalf("got %d spans", len(spans))
	}
	attrs := map[string]string{}
	for _, attr := range spans[0].Attributes {
		attrs[string(attr.Key)] = attr.Value.AsString()
	}
	if attrs["model"] != "test-model" || attrs["run_id"] != "run-1" {
		t.Fatalf("missing safe attributes: %#v", attrs)
	}
	if _, ok := attrs["prompt"]; ok {
		t.Fatal("prompt leaked into span")
	}
	if _, ok := attrs["authorization"]; ok {
		t.Fatal("authorization leaked into span")
	}
}

func TestTelemetryPropagatesW3CTraceContext(t *testing.T) {
	otel.SetTextMapPropagator(propagation.TraceContext{})
	exporter := tracetest.NewInMemoryExporter()
	provider := sdktrace.NewTracerProvider(sdktrace.WithSyncer(exporter))
	telemetry := &Telemetry{enabled: true, tracer: provider.Tracer("test")}
	ctx, span := telemetry.StartRun(context.Background(), "run-1", "corr-1", "model")
	defer span.End()
	if telemetry.TraceID(ctx) == "" {
		t.Fatal("missing trace id")
	}
	headers := make(http.Header)
	telemetry.Inject(ctx, headers)
	extracted := otel.GetTextMapPropagator().Extract(context.Background(), propagation.HeaderCarrier(headers))
	if got := traceID(extracted); got != telemetry.TraceID(ctx) {
		t.Fatalf("trace context mismatch: %s != %s", got, telemetry.TraceID(ctx))
	}
}

func TestTelemetryDisabledWithoutEndpoint(t *testing.T) {
	t.Setenv("UAI_OTEL_ENDPOINT", "")
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
	telemetry := NewTelemetry("test")
	if telemetry.enabled || telemetry.TraceID(context.Background()) != "" {
		t.Fatal("telemetry should be a no-op without endpoint")
	}
}

func TestSanitizeRouteReplacesUUIDs(t *testing.T) {
	route := sanitizeRoute("/v1/conversations/00000000-0000-4000-8000-000000000001/messages")
	if route != "/v1/conversations/{id}/messages" {
		t.Fatalf("unexpected route: %s", route)
	}
}

package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"regexp"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetrichttp"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/propagation"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
	"go.opentelemetry.io/otel/trace"
)

type Telemetry struct {
	enabled  bool
	tracer   trace.Tracer
	meter    metric.Meter
	requests metric.Int64Counter
	duration metric.Float64Histogram
	events   metric.Int64Counter
	tokens   metric.Int64Counter
	errors   metric.Int64Counter
	traces   *sdktrace.TracerProvider
	metrics  *sdkmetric.MeterProvider
}

var uuidPath = regexp.MustCompile(`[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}`)

func sanitizeRoute(path string) string {
	return uuidPath.ReplaceAllString(path, "{id}")
}

func telemetryAttributes(attrs ...attribute.KeyValue) []attribute.KeyValue {
	out := make([]attribute.KeyValue, 0, len(attrs))
	for _, attr := range attrs {
		key := strings.ToLower(string(attr.Key))
		if strings.Contains(key, "prompt") || strings.Contains(key, "message") ||
			strings.Contains(key, "content") || strings.Contains(key, "authorization") ||
			strings.Contains(key, "cookie") || strings.Contains(key, "token") ||
			strings.Contains(key, "password") || strings.Contains(key, "secret") ||
			strings.Contains(key, "credential") || strings.Contains(key, "api_key") {
			continue
		}
		value := attr.Value.AsString()
		if len(value) > 200 {
			value = value[:200]
		}
		out = append(out, attribute.String(key, value))
	}
	return out
}

func NewTelemetry(service string) *Telemetry {
	t := &Telemetry{}
	endpoint := os.Getenv("UAI_OTEL_ENDPOINT")
	if endpoint == "" {
		endpoint = os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	}
	if endpoint == "" {
		return t
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	resource, err := resource.New(ctx, resource.WithAttributes(
		semconv.ServiceName(service),
	))
	if err != nil {
		return t
	}
	traceExporter, err := otlptracehttp.New(ctx, otlptracehttp.WithEndpointURL(endpoint+"/v1/traces"))
	if err != nil {
		return t
	}
	metricExporter, err := otlpmetrichttp.New(ctx, otlpmetrichttp.WithEndpointURL(endpoint+"/v1/metrics"))
	if err != nil {
		return t
	}
	t.traces = sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(traceExporter),
		sdktrace.WithResource(resource),
	)
	t.metrics = sdkmetric.NewMeterProvider(
		sdkmetric.WithReader(sdkmetric.NewPeriodicReader(metricExporter)),
		sdkmetric.WithResource(resource),
	)
	otel.SetTracerProvider(t.traces)
	otel.SetMeterProvider(t.metrics)
	otel.SetTextMapPropagator(propagation.TraceContext{})
	t.tracer = t.traces.Tracer(service)
	t.meter = t.metrics.Meter(service)
	t.enabled = true
	t.requests, _ = t.meter.Int64Counter("uai.requests")
	t.duration, _ = t.meter.Float64Histogram("uai.request.duration", metric.WithUnit("s"))
	t.events, _ = t.meter.Int64Counter("uai.events")
	t.tokens, _ = t.meter.Int64Counter("uai.tokens")
	t.errors, _ = t.meter.Int64Counter("uai.errors")
	return t
}

func (t *Telemetry) Start(ctx context.Context, name string, attrs ...attribute.KeyValue) (context.Context, trace.Span) {
	if !t.enabled || t.tracer == nil {
		return ctx, trace.SpanFromContext(ctx)
	}
	return t.tracer.Start(ctx, name, trace.WithAttributes(telemetryAttributes(attrs...)...))
}

func (t *Telemetry) StartRun(ctx context.Context, runID, correlationID, model string) (context.Context, trace.Span) {
	return t.Start(ctx, "gateway.runtime", attribute.String("run_id", runID),
		attribute.String("correlation_id", correlationID), attribute.String("model", model))
}

func (t *Telemetry) Inject(ctx context.Context, headers http.Header) {
	if t.enabled {
		otel.GetTextMapPropagator().Inject(ctx, propagation.HeaderCarrier(headers))
	}
}

func (t *Telemetry) TraceID(ctx context.Context) string {
	span := trace.SpanFromContext(ctx)
	if span.SpanContext().IsValid() {
		return span.SpanContext().TraceID().String()
	}
	return ""
}

func (t *Telemetry) RecordRequest(method, route string, status int, seconds float64) {
	if !t.enabled {
		return
	}
	route = sanitizeRoute(route)
	attrs := metric.WithAttributes(attribute.String("method", method), attribute.String("route", route), attribute.Int("status", status))
	t.requests.Add(context.Background(), 1, attrs)
	t.duration.Record(context.Background(), seconds, metric.WithAttributes(attribute.String("route", route), attribute.Int("status", status)))
}

func (t *Telemetry) RecordEvent(eventType string, terminal bool) {
	if !t.enabled {
		return
	}
	t.events.Add(context.Background(), 1, metric.WithAttributes(
		attribute.String("event_type", eventType), attribute.Bool("terminal", terminal)))
}

func (t *Telemetry) RecordTokens(model string, input, output int) {
	if !t.enabled || (input == 0 && output == 0) {
		return
	}
	if len(model) > 100 {
		model = model[:100]
	}
	if input > 0 {
		t.tokens.Add(context.Background(), int64(input), metric.WithAttributes(
			attribute.String("model", model), attribute.String("direction", "input")))
	}
	if output > 0 {
		t.tokens.Add(context.Background(), int64(output), metric.WithAttributes(
			attribute.String("model", model), attribute.String("direction", "output")))
	}
}

func (t *Telemetry) RecordError(code, operation string) {
	if !t.enabled {
		return
	}
	t.errors.Add(context.Background(), 1, metric.WithAttributes(
		attribute.String("code", code), attribute.String("operation", operation)))
}

func (t *Telemetry) Shutdown(ctx context.Context) {
	if t.traces != nil {
		_ = t.traces.Shutdown(ctx)
	}
	if t.metrics != nil {
		_ = t.metrics.Shutdown(ctx)
	}
}

type statusWriter struct {
	http.ResponseWriter
	status int
}

func (w *statusWriter) WriteHeader(status int) {
	w.status = status
	w.ResponseWriter.WriteHeader(status)
}

func (w *statusWriter) Flush() {
	if flusher, ok := w.ResponseWriter.(http.Flusher); ok {
		flusher.Flush()
	}
}

func (w *statusWriter) Unwrap() http.ResponseWriter {
	return w.ResponseWriter
}

func (s *server) telemetryMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		parent := otel.GetTextMapPropagator().Extract(r.Context(), propagation.HeaderCarrier(r.Header))
		ctx, span := s.telemetry.Start(parent, r.Method+" "+sanitizeRoute(r.URL.Path),
			attribute.String("http.method", r.Method), attribute.String("http.route", sanitizeRoute(r.URL.Path)))
		defer span.End()
		if traceID := s.telemetry.TraceID(ctx); traceID != "" {
			w.Header().Set("X-Trace-ID", traceID)
		}
		start := time.Now()
		writer := &statusWriter{ResponseWriter: w, status: 200}
		next.ServeHTTP(writer, r.WithContext(ctx))
		route := chiRoutePattern(ctx)
		s.telemetry.RecordRequest(r.Method, route, writer.status, time.Since(start).Seconds())
		slog.Info("http_request", "method", r.Method, "route", route, "status", writer.status,
			"trace_id", s.telemetry.TraceID(ctx), "duration_ms", time.Since(start).Milliseconds())
	})
}

func chiRoutePattern(ctx context.Context) string {
	// Filled by the chi route context after routing; fall back to the raw path.
	if pattern := chi.RouteContext(ctx).RoutePattern(); pattern != "" {
		return pattern
	}
	return "/"
}

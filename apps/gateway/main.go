package main

import (
	"context"
	"encoding/hex"
	"log"
	"log/slog"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))
	rateLimit := 120
	if value := os.Getenv("UAI_RATE_LIMIT"); value != "" {
		n, err := strconv.Atoi(value)
		if err != nil || n < 1 {
			log.Fatal("invalid rate limit")
		}
		rateLimit = n
	}
	perPrincipalLimit := 120
	if value := os.Getenv("UAI_RATE_LIMIT_PER_PRINCIPAL"); value != "" {
		n, err := strconv.Atoi(value)
		if err != nil || n < 1 {
			log.Fatal("invalid per-principal rate limit")
		}
		perPrincipalLimit = n
	}
	widgetRateLimit := 60
	if value := os.Getenv("UAI_WIDGET_RATE_LIMIT"); value != "" {
		n, err := strconv.Atoi(value)
		if err != nil || n < 1 {
			log.Fatal("invalid widget rate limit")
		}
		widgetRateLimit = n
	}
	widgetOrigins := parseWidgetOrigins(os.Getenv("UAI_WIDGET_ORIGINS"))
	for _, origin := range widgetOrigins {
		if !validWidgetOrigin(origin) {
			log.Fatal("invalid widget origin")
		}
	}
	retentionDays := func(name string) int {
		value := os.Getenv(name)
		if value == "" {
			return 0
		}
		n, err := strconv.Atoi(value)
		if err != nil || n < 0 {
			log.Fatal("invalid retention policy")
		}
		return n
	}
	apiKeyHash, e := secretFromEnv("UAI_API_KEY_SHA256")
	if e != nil {
		log.Fatal("invalid secret configuration")
	}
	internalKey, e := secretFromEnv("INTERNAL_API_KEY")
	if e != nil {
		log.Fatal("invalid secret configuration")
	}
	databaseURL, e := secretFromEnv("DATABASE_URL")
	if e != nil {
		log.Fatal("invalid secret configuration")
	}
	c := Config{
		APIKeyHash: apiKeyHash, InternalKey: internalKey,
		RuntimeURL: os.Getenv("RUNTIME_URL"), Model: os.Getenv("MODEL_NAME"), RateLimit: rateLimit,
		RateLimitPerPrincipal: perPrincipalLimit,
		WidgetRateLimit:       widgetRateLimit, WidgetOrigins: widgetOrigins,
		RetentionConversationDays: retentionDays("UAI_RETENTION_CONVERSATION_DAYS"),
		RetentionAuditDays:        retentionDays("UAI_RETENTION_AUDIT_DAYS"),
		RetentionApprovalDays:     retentionDays("UAI_RETENTION_APPROVAL_DAYS"),
		RetentionCleanupDays:      retentionDays("UAI_RETENTION_CLEANUP_DAYS"),
	}
	digest, e := hex.DecodeString(c.APIKeyHash)
	if (c.APIKeyHash != "" && (e != nil || len(digest) != 32)) || len(c.InternalKey) < 32 || c.Model == "" {
		log.Fatal("invalid authentication or model configuration")
	}
	u, e := url.Parse(c.RuntimeURL)
	if e != nil || u.Host == "" || u.User != nil || (u.Scheme != "http" && u.Scheme != "https") {
		log.Fatal("invalid runtime URL")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	s, e := OpenStore(ctx, databaseURL)
	cancel()
	if e != nil {
		log.Fatal("database initialization failed")
	}
	defer s.pool.Close()
	if c.APIKeyHash == "" {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		exists, err := s.HasActiveAdmin(ctx)
		cancel()
		if err != nil || !exists {
			log.Fatal("configure bootstrap key or active admin credential")
		}
	}
	catalogCtx, catalogCancel := context.WithTimeout(context.Background(), 10*time.Second)
	models, catalogErr := loadRuntimeModels(catalogCtx, c)
	if catalogErr == nil {
		catalogErr = s.SyncModels(catalogCtx, models)
	}
	catalogCancel()
	if catalogErr != nil {
		log.Fatal("runtime model catalog initialization failed")
	}

	handler := NewServer(s, c)
	defer handler.telemetry.Shutdown(context.Background())
	pluginCtx, pluginCancel := context.WithTimeout(context.Background(), 15*time.Second)
	pluginConfig, pluginErr := s.PluginConfiguration(pluginCtx)
	if pluginErr == nil {
		var applied bool
		applied, pluginErr = handler.reconcilePluginConfiguration(pluginCtx, pluginConfig)
		if !applied {
			log.Print("plugin configuration pending; inspect administrative plugin status")
		}
	}
	pluginCancel()
	if pluginErr != nil {
		log.Print("plugin reconciliation pending; administrative retry required")
	}
	srv := &http.Server{Addr: ":8080", Handler: handler, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 10 * time.Second, IdleTimeout: 60 * time.Second, MaxHeaderBytes: 16 * 1024}
	stop, done := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer done()
	shutdownDone := make(chan struct{})
	go func() {
		defer close(shutdownDone)
		<-stop.Done()
		ctx, c := context.WithTimeout(context.Background(), 140*time.Second)
		defer c()
		if err := srv.Shutdown(ctx); err != nil {
			log.Print("graceful shutdown timed out")
			srv.Close()
		}
	}()
	log.Print("gateway listening on :8080")
	if e = srv.ListenAndServe(); e != nil && e != http.ErrServerClosed {
		log.Fatal("gateway stopped unexpectedly")
	}
	<-shutdownDone
}

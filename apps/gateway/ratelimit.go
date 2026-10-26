package main

import (
	"sync"
	"time"
)

const maxRateLimitKeys = 10000

type rateWindow struct {
	start time.Time
	count int
}

// rateLimiter is a bounded fixed-window limiter. Expired entries are swept
// before a new key is rejected, so capacity can never grow without bound.
type rateLimiter struct {
	mu      sync.Mutex
	limit   int
	window  time.Duration
	maxKeys int
	entries map[string]rateWindow
}

func newRateLimiter(limit, maxKeys int) *rateLimiter {
	if maxKeys < 1 {
		maxKeys = 1
	}
	return &rateLimiter{limit: limit, window: time.Minute, maxKeys: maxKeys,
		entries: map[string]rateWindow{}}
}

func (l *rateLimiter) allow(key string, now time.Time) bool {
	if l.limit <= 0 {
		return true
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	entry, exists := l.entries[key]
	if !exists || now.Sub(entry.start) >= l.window || now.Before(entry.start) {
		if !exists && len(l.entries) >= l.maxKeys {
			l.sweep(now)
			if len(l.entries) >= l.maxKeys {
				return false
			}
		}
		entry = rateWindow{start: now}
	}
	entry.count++
	l.entries[key] = entry
	return entry.count <= l.limit
}

func (l *rateLimiter) sweep(now time.Time) {
	for key, entry := range l.entries {
		if now.Sub(entry.start) >= l.window || now.Before(entry.start) {
			delete(l.entries, key)
		}
	}
}

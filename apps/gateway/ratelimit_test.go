package main

import (
	"testing"
	"time"
)

func TestRateLimiterSeparatesKeys(t *testing.T) {
	l := newRateLimiter(2, 10)
	now := time.Unix(1000, 0)
	for i := 0; i < 2; i++ {
		if !l.allow("a", now) {
			t.Fatalf("a request %d denied", i+1)
		}
	}
	if l.allow("a", now) {
		t.Fatal("a exceeded its limit")
	}
	if !l.allow("b", now) {
		t.Fatal("b must have an independent budget")
	}
}

func TestRateLimiterResetsWindow(t *testing.T) {
	l := newRateLimiter(1, 10)
	now := time.Unix(1000, 0)
	if !l.allow("a", now) {
		t.Fatal("first request denied")
	}
	if l.allow("a", now.Add(30*time.Second)) {
		t.Fatal("request inside the window allowed")
	}
	if !l.allow("a", now.Add(time.Minute)) {
		t.Fatal("new window denied")
	}
}

func TestRateLimiterBoundsStorage(t *testing.T) {
	l := newRateLimiter(5, 2)
	now := time.Unix(1000, 0)
	if !l.allow("a", now) || !l.allow("b", now) {
		t.Fatal("initial keys denied")
	}
	if l.allow("c", now) {
		t.Fatal("new key admitted at capacity")
	}
	if !l.allow("a", now.Add(time.Second)) {
		t.Fatal("existing key denied at capacity")
	}
	if !l.allow("c", now.Add(time.Minute)) {
		t.Fatal("new key denied after expired entries were swept")
	}
	if len(l.entries) > l.maxKeys {
		t.Fatalf("storage grew to %d", len(l.entries))
	}
}

func TestRateLimiterHandlesClockGoingBackwards(t *testing.T) {
	l := newRateLimiter(1, 2)
	now := time.Unix(1000, 0)
	l.allow("a", now)
	if !l.allow("a", now.Add(-time.Minute)) {
		t.Fatal("backwards clock must start a new window")
	}
}

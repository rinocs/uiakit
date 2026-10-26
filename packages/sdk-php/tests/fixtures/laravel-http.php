<?php
// Only for SDK tests without illuminate/http; real Laravel uses its own HTTP classes.
namespace Illuminate\Http;
if (!class_exists(Request::class)) {
    class Request {
        public function __construct(private mixed $identity = null, private ?string $origin = null) {}
        public function user(): mixed { return $this->identity; }
        public function header(string $name): ?string { return $this->origin; }
    }
    class JsonResponse {
        public function __construct(public array $data, public int $status = 200, public array $headers = []) {}
        public function getStatusCode(): int { return $this->status; }
        public function getData(bool $assoc = false): mixed { return $assoc ? $this->data : (object) $this->data; }
    }
}

<?php

declare(strict_types=1);

namespace UniversalAIKit;

use JsonException;
use UniversalAIKit\Exception\ApiException;
use UniversalAIKit\Exception\ResponseException;
use UniversalAIKit\Exception\StreamProtocolException;
use UniversalAIKit\Exception\TimeoutException;
use UniversalAIKit\Exception\TransportException;
use UniversalAIKit\Exception\ValidationException;

final class Client
{
    private readonly string $baseUrl;

    public function __construct(
        string $baseUrl,
        private readonly string $apiKey,
        private readonly int $timeoutMs = 30000,
    ) {
        $this->baseUrl = rtrim(trim($baseUrl), '/');
        if ($this->baseUrl === '') {
            throw new ValidationException('baseUrl is required.');
        }
        if (trim($this->apiKey) === '') {
            throw new ValidationException('apiKey is required.');
        }
        if ($this->timeoutMs <= 0) {
            throw new ValidationException('timeoutMs must be positive.');
        }
    }

    public function health(): mixed
    {
        return $this->request('health');
    }

    /** @return array<string, mixed> */
    public function me(): array
    {
        return $this->request('me');
    }

    /** @return list<array<string, mixed>> */
    public function listAssistants(): array
    {
        return $this->request('listAssistants');
    }

    /** @param array<string, mixed> $input
     *  @return array<string, mixed>
     */
    public function createAssistant(array $input): array
    {
        return $this->request('createAssistant', body: $input);
    }

    /** @return array<string, mixed> */
    public function getAssistant(string $id): array
    {
        return $this->request('getAssistant', ['id' => $id]);
    }

    /** @param array<string, mixed> $patch
     *  @return array<string, mixed>
     */
    public function updateAssistant(string $id, array $patch, string $ifMatch): array
    {
        return $this->request('updateAssistant', ['id' => $id], body: $patch, headers: ['If-Match' => $ifMatch]);
    }

    /** @return list<array<string, mixed>> */
    public function listAssistantVersions(string $id): array
    {
        return $this->request('listAssistantVersions', ['id' => $id]);
    }

    /** @param array<string, mixed> $input
     *  @return array<string, mixed>
     */
    public function createConversation(array $input): array
    {
        return $this->request('createConversation', body: $input);
    }

    public function deleteConversation(string $conversationId): void
    {
        $this->request('deleteConversation', ['id' => $conversationId]);
    }

    /** @return list<array<string, mixed>> */
    public function getMessages(string $conversationId): array
    {
        return $this->request('getMessages', ['id' => $conversationId]);
    }

    /**
     * Opens the SSE stream. Iterate the returned MessageStream exactly once.
     *
     * @param array<string, mixed> $input
     */
    public function streamMessage(string $conversationId, array $input, string $idempotencyKey): MessageStream
    {
        if (trim($idempotencyKey) === '') {
            throw new ValidationException('Idempotency-Key is required for sendMessage.');
        }
        $operation = Operations::ALL['sendMessage'];
        $path = $this->fillPath($operation['path'], ['id' => $conversationId]);
        try {
            $body = json_encode($input, JSON_THROW_ON_ERROR);
        } catch (JsonException $exception) {
            throw new ValidationException('Message input cannot be encoded.', 0, $exception);
        }
        $headers = $this->headerLines([
            'Authorization' => 'Bearer ' . $this->apiKey,
            'Accept' => 'text/event-stream',
            'Content-Type' => 'application/json',
            'Idempotency-Key' => $idempotencyKey,
        ]);
        $context = stream_context_create([
            'http' => [
                'method' => 'POST',
                'header' => implode("\r\n", $headers),
                'content' => $body,
                'timeout' => $this->timeoutMs / 1000,
                'ignore_errors' => true,
                'follow_location' => 0,
                'max_redirects' => 0,
            ],
        ]);
        $handle = @fopen($this->baseUrl . $path, 'rb', false, $context);
        if ($handle === false) {
            throw new TransportException('Cannot open SSE stream.');
        }
        $responseHeaders = $http_response_header ?? [];
        $status = $this->responseStatus($responseHeaders);
        $headersMap = $this->headerMap($responseHeaders);
        if ($status < 200 || $status >= 300) {
            $raw = stream_get_contents($handle);
            fclose($handle);
            throw ApiException::fromResponse($status, is_string($raw) ? $raw : '');
        }
        if (! str_starts_with(strtolower($headersMap['content-type'] ?? ''), 'text/event-stream')) {
            fclose($handle);
            throw new StreamProtocolException('Gateway did not return an SSE stream.');
        }
        $runId = $headersMap['x-run-id'] ?? '';
        if ($runId === '') {
            fclose($handle);
            throw new StreamProtocolException('Gateway did not return X-Run-ID.');
        }
        $assistantVersion = isset($headersMap['x-assistant-version'])
            ? (int) $headersMap['x-assistant-version']
            : null;
        stream_set_blocking($handle, true);
        stream_set_timeout($handle, intdiv($this->timeoutMs, 1000), ($this->timeoutMs % 1000) * 1000);

        return new MessageStream($handle, $runId, $assistantVersion);
    }

    /** @return list<array<string, mixed>> */
    public function listCredentials(): array
    {
        return $this->request('listCredentials');
    }

    /** @param array<string, mixed> $input
     *  @return array<string, mixed>
     */
    public function createCredential(array $input): array
    {
        return $this->request('createCredential', body: $input);
    }

    /** @param array<string, mixed> $input
     *  @return array<string, mixed>
     */
    public function rotateCredential(string $id, array $input): array
    {
        return $this->request('rotateCredential', ['id' => $id], body: $input);
    }

    /** @return array<string, mixed> */
    public function revokeCredential(string $id): array
    {
        return $this->request('revokeCredential', ['id' => $id]);
    }

    /** @return list<array<string, mixed>> */
    public function listModels(): array
    {
        return $this->request('listModels');
    }

    /** @return list<array<string, mixed>> */
    public function listTools(): array
    {
        return $this->request('listTools');
    }

    /** @return array<string, mixed> */
    public function listPlugins(): array
    {
        return $this->request('listPlugins');
    }

    /** @param array<string, mixed> $setting
     *  @return array<string, mixed>
     */
    public function configurePlugin(string $id, array $setting, string $ifMatch): array
    {
        return $this->request('configurePlugin', ['id' => $id], body: $setting, headers: ['If-Match' => $ifMatch]);
    }

    /** @return array<string, mixed> */
    public function removePluginConfiguration(string $id, string $ifMatch): array
    {
        return $this->request('removePluginConfiguration', ['id' => $id], headers: ['If-Match' => $ifMatch]);
    }

    /** @return array<string, mixed> */
    public function pluginHealth(string $id): array
    {
        return $this->request('pluginHealth', ['id' => $id]);
    }

    /** @return list<array<string, mixed>> */
    public function listKnowledgeBases(): array
    {
        return $this->request('listKnowledgeBases');
    }

    /** @param array<string, mixed> $input
     *  @return array<string, mixed>
     */
    public function createKnowledgeBase(array $input): array
    {
        return $this->request('createKnowledgeBase', body: $input);
    }

    /** @return array<string, mixed> */
    public function getKnowledgeBase(string $id): array
    {
        return $this->request('getKnowledgeBase', ['id' => $id]);
    }

    /** @param array<string, mixed> $patch
     *  @return array<string, mixed>
     */
    public function updateKnowledgeBase(string $id, array $patch, string $ifMatch): array
    {
        return $this->request('updateKnowledgeBase', ['id' => $id], body: $patch, headers: ['If-Match' => $ifMatch]);
    }

    public function deleteKnowledgeBase(string $id, string $ifMatch): void
    {
        $this->request('deleteKnowledgeBase', ['id' => $id], headers: ['If-Match' => $ifMatch]);
    }

    /** @return list<array<string, mixed>> */
    public function listKnowledgeBaseVersions(string $id): array
    {
        return $this->request('listKnowledgeBaseVersions', ['id' => $id]);
    }

    /** @param array<string, mixed> $input
     *  @return array<string, mixed>
     */
    public function createKnowledgeBaseVersion(string $id, array $input, string $ifMatch): array
    {
        return $this->request('createKnowledgeBaseVersion', ['id' => $id], body: $input, headers: ['If-Match' => $ifMatch]);
    }

    /** @return array<string, mixed> */
    public function exportKnowledgeBase(string $id): array
    {
        return $this->request('exportKnowledgeBase', ['id' => $id]);
    }

    /** @return list<array<string, mixed>> */
    public function listDocuments(?string $knowledgeBaseId = null): array
    {
        return $this->request('listDocuments', query: $knowledgeBaseId === null ? [] : ['knowledge_base_id' => $knowledgeBaseId]);
    }

    /** @return array<string, mixed> */
    public function uploadDocument(
        string $knowledgeBaseId,
        string $filename,
        string $contents,
        ?string $title = null,
    ): array {
        if (trim($knowledgeBaseId) === '') {
            throw new ValidationException('knowledge base id is required.');
        }
        if ($filename === '') {
            throw new ValidationException('filename is required.');
        }
        $fields = [
            'knowledge_base_id' => $knowledgeBaseId,
            'file' => new \CURLStringFile($contents, $filename, 'application/octet-stream'),
        ];
        if ($title !== null) {
            $fields['title'] = $title;
        }
        $operation = Operations::ALL['uploadDocument'];
        $raw = $this->execute(
            $operation['method'],
            $this->baseUrl . $operation['path'],
            $this->headerLines(['Authorization' => 'Bearer ' . $this->apiKey, 'Accept' => 'application/json']),
            $fields,
        );

        return $this->decodeJson($raw);
    }

    /** @return array<string, mixed> */
    public function getDocument(string $id): array
    {
        return $this->request('getDocument', ['id' => $id]);
    }

    public function deleteDocument(string $id): void
    {
        $this->request('deleteDocument', ['id' => $id]);
    }

    /** @return array<string, mixed> */
    public function getDocumentJob(string $id): array
    {
        return $this->request('getDocumentJob', ['id' => $id]);
    }

    /** @return array<string, mixed> */
    public function cancelDocumentJob(string $id): array
    {
        return $this->request('cancelDocumentJob', ['id' => $id]);
    }

    /** @return list<array<string, mixed>> */
    public function listAgentRuns(): array
    {
        return $this->request('listAgentRuns');
    }

    /** @return array<string, mixed> */
    public function getAgentRun(string $id): array
    {
        return $this->request('getAgentRun', ['id' => $id]);
    }

    /** @return array<string, mixed> */
    public function cancelAgentRun(string $id): array
    {
        return $this->request('cancelAgentRun', ['id' => $id]);
    }

    /** @return list<array<string, mixed>> */
    public function listApprovals(): array
    {
        return $this->request('listApprovals');
    }

    /** @return array<string, mixed> */
    public function getApproval(string $id): array
    {
        return $this->request('getApproval', ['id' => $id]);
    }

    /** @return array<string, mixed> */
    public function approveApproval(string $id): array
    {
        return $this->request('approveApproval', ['id' => $id]);
    }

    /** @return array<string, mixed> */
    public function rejectApproval(string $id): array
    {
        return $this->request('rejectApproval', ['id' => $id]);
    }

    /** @return list<array<string, mixed>> */
    public function listAuditEvents(): array
    {
        return $this->request('listAuditEvents');
    }

    /** @param array<string, mixed> $input
     *  @return array<string, mixed>
     */
    public function createWidgetToken(array $input): array
    {
        return $this->request('createWidgetToken', body: $input);
    }

    /** @return array<string, mixed> */
    public function revokeWidgetToken(string $id): array
    {
        return $this->request('revokeWidgetToken', ['id' => $id]);
    }

    /**
     * @param array<string, string> $pathParams
     * @param array<string, scalar> $query
     * @param array<string, mixed>|null $body
     * @param array<string, string> $headers
     */
    public function request(
        string $operationId,
        array $pathParams = [],
        array $query = [],
        ?array $body = null,
        array $headers = [],
    ): mixed {
        $operation = Operations::ALL[$operationId] ?? null;
        if ($operation === null) {
            throw new ValidationException('Unknown operation ' . $operationId . '.');
        }
        if (($operation['idempotency'] ?? false) && trim($this->headerValue($headers, 'Idempotency-Key') ?? '') === '') {
            throw new ValidationException('Idempotency-Key is required for ' . $operationId . '.');
        }
        if (($operation['ifMatch'] ?? false) && trim($this->headerValue($headers, 'If-Match') ?? '') === '') {
            throw new ValidationException('If-Match is required for ' . $operationId . '.');
        }
        $path = $this->fillPath($operation['path'], $pathParams);
        $url = $this->baseUrl . $path;
        if ($query !== []) {
            $url .= '?' . http_build_query($query, '', '&', PHP_QUERY_RFC3986);
        }
        $requestHeaders = ['Authorization' => 'Bearer ' . $this->apiKey, 'Accept' => 'application/json'];
        foreach ($headers as $name => $value) {
            $requestHeaders[$name] = $value;
        }
        $payload = null;
        if ($body !== null) {
            try {
                $payload = json_encode($body, JSON_THROW_ON_ERROR);
            } catch (JsonException $exception) {
                throw new ValidationException('Request body cannot be encoded.', 0, $exception);
            }
            if ($this->headerValue($requestHeaders, 'Content-Type') === null) {
                $requestHeaders['Content-Type'] = 'application/json';
            }
        }
        $raw = $this->execute(
            $operation['method'],
            $url,
            $this->headerLines($requestHeaders),
            $payload,
        );
        if ($raw === '') {
            return null;
        }

        return $this->decodeJson($raw);
    }

    /**
     * @param list<string> $headers
     * @param string|array<string, mixed>|null $body
     */
    private function execute(string $method, string $url, array $headers, string|array|null $body): string
    {
        $handle = curl_init();
        if ($handle === false) {
            throw new TransportException('Cannot initialize cURL.');
        }
        $options = [
            CURLOPT_URL => $url,
            CURLOPT_CUSTOMREQUEST => $method,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_HTTPHEADER => $headers,
            CURLOPT_CONNECTTIMEOUT_MS => min($this->timeoutMs, 10000),
            CURLOPT_TIMEOUT_MS => $this->timeoutMs,
            CURLOPT_FOLLOWLOCATION => false,
        ];
        if ($body !== null) {
            $options[CURLOPT_POSTFIELDS] = $body;
        }
        curl_setopt_array($handle, $options);
        $raw = curl_exec($handle);
        $status = (int) curl_getinfo($handle, CURLINFO_RESPONSE_CODE);
        $errorNumber = curl_errno($handle);
        $error = curl_error($handle);
        if ($raw === false) {
            if ($errorNumber === CURLE_OPERATION_TIMEDOUT) {
                throw new TimeoutException('Gateway request timed out.');
            }
            throw new TransportException('Gateway request failed: ' . $error);
        }
        if ($status < 200 || $status >= 300) {
            throw ApiException::fromResponse($status, is_string($raw) ? $raw : '');
        }

        return is_string($raw) ? $raw : '';
    }

    /** @return array<string, mixed> */
    private function decodeJson(string $raw): array
    {
        if ($raw === '') {
            return [];
        }
        try {
            $decoded = json_decode($raw, true, 512, JSON_THROW_ON_ERROR);
        } catch (JsonException $exception) {
            throw new ResponseException('Gateway returned invalid JSON.', 0, $exception);
        }
        if (! is_array($decoded)) {
            throw new ResponseException('Gateway response must be a JSON object.');
        }

        return $decoded;
    }

    /** @param array<string, string> $pathParams */
    private function fillPath(string $path, array $pathParams): string
    {
        foreach ($pathParams as $name => $value) {
            $path = str_replace('{' . $name . '}', rawurlencode($value), $path);
        }
        if (str_contains($path, '{')) {
            throw new ValidationException('Missing path parameter for ' . $path . '.');
        }

        return $path;
    }

    /** @param array<string, string> $headers @return list<string> */
    private function headerLines(array $headers): array
    {
        $lines = [];
        foreach ($headers as $name => $value) {
            $lines[] = $name . ': ' . $value;
        }

        return $lines;
    }

    /** @param array<string, string> $headers */
    private function headerValue(array $headers, string $name): ?string
    {
        foreach ($headers as $key => $value) {
            if (strcasecmp($key, $name) === 0) {
                return $value;
            }
        }

        return null;
    }

    /** @param list<string> $lines */
    private function responseStatus(array $lines): int
    {
        foreach ($lines as $line) {
            if (preg_match('/^HTTP\/\S+\s+(\d{3})/', $line, $matches) === 1) {
                return (int) $matches[1];
            }
        }

        return 0;
    }

    /** @param list<string> $lines @return array<string, string> */
    private function headerMap(array $lines): array
    {
        $map = [];
        foreach ($lines as $line) {
            $separator = strpos($line, ':');
            if ($separator === false) {
                continue;
            }
            $name = strtolower(trim(substr($line, 0, $separator)));
            $map[$name] = trim(substr($line, $separator + 1));
        }

        return $map;
    }
}

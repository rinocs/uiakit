# Widget examples

All examples expect a same-origin backend endpoint `POST /api/widget-token`
that mints a widget token with the server-side admin credential:

```php
// Laravel route sketch
Route::post('/api/widget-token', function (UniversalAIKit\Client $client) {
    return response()->json($client->createWidgetToken([
        'assistant_id' => config('support.assistant_id'),
        'conversation_id' => config('support.conversation_id'),
        'subject' => 'web-session-' . auth()->id(),
        'origin' => config('app.url'),
        'expires_in_seconds' => 900,
    ]));
})->middleware('auth');
```

Rules:

- the admin key stays in the backend environment;
- the browser receives only the short-lived widget token and conversation id;
- the token is bound to origin, assistant and conversation by the gateway;
- never put a token in a URL, analytics event or log.

Files:

- `vanilla.html`: import map + Web Component, no framework.
- `react.jsx`: ref + `setConfig`, no fork of the widget.
- `svelte.svelte`: `bind:this` + `setConfig`, no fork of the widget.

Build first:

```bash
npm run build --prefix packages/chat-widget
```

Then serve the repository root with any static server and open
`/examples/widget/vanilla.html` (with the backend token endpoint available).

# Laravel examples

Follow [the Laravel integration guide](../../docs/laravel.md) to install the PHP
SDK and shared browser widget in an existing authenticated Laravel application.

- `routes/web.php`: private, CSRF-protected widget session endpoint with auth and throttling.
- `resources/js/chat.js`: Vite module connecting every Blade chat component using the host CSRF token.
- `routes/api.php`: existing authenticated server-side streaming proxy example; its API is unchanged.

The package provider registers no routes. Merge the chosen example into the
host application and retain its web middleware, authentication and authorization.

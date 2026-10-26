# Console graphite-orange

Approved direction: professional graphite-orange console with persistent appearance preferences and operational configuration already supported by the runtime.

Approaches considered: extend the console over existing APIs (selected); add deployment configuration APIs (deferred because it requires a separate secret-management and service-reconfiguration design).

Keep the SvelteKit architecture and existing authentication, version history, If-Match concurrency protection, authorization and deployment-owned credentials. Group navigation by task, use graphite surfaces and orange actions, improve tables/forms and mobile navigation. Add a settings page for dark/light/system theme and comfortable/compact density, persisted in a validated browser cookie and applied during SSR.

Extend assistant configuration with description, declared tools, knowledge bases, conversation memory and execution limits. Unsupported semantic memory/skills and disabling tool approval must remain unavailable. Preserve selected resources absent from the current catalog. Optional catalog failures must not prevent editing other fields or clear existing selections. Failed submissions retain entered values. Runtime remains the authority for resource authorization.

No new dependencies, deployment mutation, secrets in browser storage, or public API changes.

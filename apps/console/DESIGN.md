# Console design

Mode: Operate. The console configures assistants and resources and monitors execution. Product behavior comes from existing routes, SDK contracts and runtime validation.

The approved direction is graphite-orange: neutral graphite surfaces, warm orange for actions and current navigation, restrained borders, clear form groups and dense but legible tables. Dark is the default; light and system themes are user preferences. Comfortable and compact density apply to navigation, lists and tables. Preferences belong to this browser and are rendered on the server from a validated cookie.

Navigation groups workspace, configuration and monitoring. Settings remains available beside account controls. On narrow screens navigation scrolls horizontally within the viewport. Tables retain horizontal scrolling where columns cannot fit. Focus indicators and a skip link support keyboard use.

Use shared CSS variables in src/app.css. Orange is reserved for interaction; green and red convey outcomes. Keep system typography for the operational interface, proportional copy and monospaced identifiers/code. Do not introduce external fonts, decorative images, gradients or status claims without product evidence.

Operational forms retain versioning, optimistic concurrency and user input after failed saves. Catalog failures retain existing selections. Deployment URLs and credentials remain outside browser configuration; unsupported runtime capabilities must not be offered as working controls.

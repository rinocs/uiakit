import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

export default {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter(),
    csrf: {
      // Exact alternates of CONSOLE_ORIGIN for LAN access (build-time list;
      // process.env is not available to the config inside Docker builds).
      trustedOrigins: [
        'http://dev-ct:3000',
        'http://dev-ct.homenet.telecomitalia.it:3000',
        'http://dev-ct.local:3000',
      ],
    },
    csp: {
      mode: 'hash',
      directives: {
        'default-src': ['self'],
        'style-src': ['self', 'unsafe-inline'],
        'img-src': ['self', 'data:'],
        'script-src': ['self'],
        'connect-src': ['self'],
        'frame-ancestors': ['none'],
        'base-uri': ['none'],
        'form-action': ['self'],
      },
    },
  },
};

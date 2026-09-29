import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    // The host is supplied by the temporary Cloudflare quick tunnel.
    allowedHosts: true,
  },
});

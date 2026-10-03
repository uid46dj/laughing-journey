import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    // Support Codespaces forwarding as well as localhost.
    allowedHosts: ['.app.github.dev', 'localhost'],
  },
});

import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react-swc'
import viteJunjoPlugin from './vite-junjo-plugin'
import { analyzer } from 'vite-bundle-analyzer'

// The backend the dev server proxies API requests to
const devBackendUrl = process.env.JUNJO_DEV_BACKEND_URL || 'http://localhost:26154'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    tailwindcss(),
    react(),
    viteJunjoPlugin(),
    // Only run analyzer if ANALYZE is true
    process.env.ANALYZE ? analyzer() : undefined,
  ].filter(Boolean),
  server: {
    port: 26151,
    host: true,
    strictPort: true,
    watch: {
      usePolling: true,
    },
    // Keys match by prefix: '/api/' keeps the '/api-keys' page with the app
    proxy: {
      '/api/': devBackendUrl,
      '/health': devBackendUrl,
    },
  },
  build: {
    sourcemap: false,
  },
})

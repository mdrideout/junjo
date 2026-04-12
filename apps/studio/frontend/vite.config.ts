import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react-swc'
import viteJunjoPlugin from './vite-junjo-plugin'
import { analyzer } from 'vite-bundle-analyzer'

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
    port: 5173,
    host: true,
    strictPort: true,
    watch: {
      usePolling: true,
    },
    proxy: {
      '/api': {
        target: 'http://backend:1323',
        changeOrigin: true,
      },
      '/api_keys': {
        target: 'http://backend:1323',
        changeOrigin: true,
      },
      '/users': {
        target: 'http://backend:1323',
        changeOrigin: true,
      },
      '/sign-in': {
        target: 'http://backend:1323',
        changeOrigin: true,
      },
      '/sign-out': {
        target: 'http://backend:1323',
        changeOrigin: true,
      },
      '/auth-test': {
        target: 'http://backend:1323',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://backend:1323',
        changeOrigin: true,
      },
    },
  },
  build: {
    sourcemap: true,
  },
})

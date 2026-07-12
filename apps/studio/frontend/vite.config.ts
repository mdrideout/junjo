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
    port: 26151,
    host: true,
    strictPort: true,
    watch: {
      usePolling: true,
    },
  },
  build: {
    sourcemap: true,
  },
})

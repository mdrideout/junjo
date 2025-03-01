import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react-swc'
import svgr from 'vite-plugin-svgr'

// https://vite.dev/config/
export default defineConfig({
  plugins: [tailwindcss(), react(), svgr()],
  server: {
    port: 5173,
    host: true,
    watch: {
      usePolling: true,
    },
    hmr: {
      clientPort: 4951, // must be mapped in docker compose to 5177
    },
  },
  build: {
    sourcemap: true,
  },
})

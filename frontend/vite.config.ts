import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// SPA statique servie en prod par FastAPI (montage de frontend/dist). En dev, Vite sur
// :5173 appelle l'API sur :8000 (CORS autorisé côté FastAPI).
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: { port: 5173 },
  test: {
    environment: 'jsdom',
    globals: true,
  },
})

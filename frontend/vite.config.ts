import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// SPA statique servie en prod par FastAPI (montage de frontend/dist). En dev, Vite sur
// :5173 appelle l'API sur :8000 (CORS autorisé côté FastAPI).
//
// `base` (audit déploiement Scaleway, 2026-09-08) : certains environnements servent l'appli
// sous un sous-chemin (ex. Traefik qui route `/dev` vers ce conteneur) plutôt qu'à la racine
// du domaine — sans ce réglage, les fichiers construits référencent `/assets/...` en dur, que
// le navigateur demanderait à la racine et jamais sous `/dev/assets/...`. `VITE_BASE_PATH` est
// fourni au moment du BUILD (voir `Dockerfile`, argument `BASE_PATH`) — vide par défaut, donc
// aucun changement pour un déploiement classique à la racine.
export default defineConfig({
  base: process.env.VITE_BASE_PATH || '/',
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

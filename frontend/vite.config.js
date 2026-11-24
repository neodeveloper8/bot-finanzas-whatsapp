import { fileURLToPath } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// En desarrollo, Vite (puerto 5173) reenvía a Django (8000) lo que es del backend.
// Así React y la API parecen el MISMO sitio: la cookie de sesión viaja sola y no hay CORS.
const DJANGO = 'http://localhost:8000'

export default defineConfig(({ command }) => ({
  plugins: [react(), tailwindcss()],

  // En producción los archivos los sirve Django (whitenoise) bajo /static/panel/
  base: command === 'build' ? '/static/panel/' : '/',

  server: {
    port: 5173,
    // changeOrigin: false (OJO: la forma corta '/ruta': DJANGO lo pone en true).
    // Así Django recibe Host "localhost:5173", igual al Origin del navegador, y su
    // chequeo CSRF de origen pasa. Con true, Django ve Origin 5173 vs Host 8000 y
    // bloquea los POST/DELETE con 403, que es justo lo que debe hacer ante un CSRF.
    proxy: Object.fromEntries(
      ['/panel/api', '/panel/salir', '/panel/acceso'].map((ruta) => [
        ruta,
        { target: DJANGO, changeOrigin: false },
      ]),
    ),
  },

  build: {
    // Directo a la carpeta static de la app panel: Django la encuentra sin configurar nada
    outDir: fileURLToPath(new URL('../panel/static/panel', import.meta.url)),
    emptyOutDir: true,
    // Recharts pesa: ~200 KB comprimido en total. Para un panel personal está bien.
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      input: 'src/main.jsx', // sin index.html: el HTML lo pone la plantilla de Django
      output: {
        // Nombres FIJOS (sin hash). El hash para el caché lo agrega Django en
        // collectstatic (ManifestStaticFilesStorage): una sola fuente de verdad.
        entryFileNames: 'panel.js',
        assetFileNames: ({ names }) =>
          names?.some((n) => n.endsWith('.css')) ? 'panel.css' : 'assets/[name][extname]',
      },
    },
  },
}))

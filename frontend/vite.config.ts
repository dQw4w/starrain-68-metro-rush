import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// VITE_API_PROXY_TARGET lets you point the dev server at a backend running on
// a non-default port (e.g. during local testing) without editing this file.
const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': apiTarget,
      '/ws': { target: apiTarget.replace('http', 'ws'), ws: true },
    },
  },
  build: {
    outDir: '../backend/static',
    emptyOutDir: true,
  },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Dev modunda API isteklerini backend'e proxy'le (CORS sorunlarını önler)
    proxy: {
      '/chat': 'http://localhost:8000',
      '/status': 'http://localhost:8000',
      '/models': 'http://localhost:8000',
      '/presets': 'http://localhost:8000',
      '/hardware': 'http://localhost:8000',
      '/v1': 'http://localhost:8000',
    },
  },
})

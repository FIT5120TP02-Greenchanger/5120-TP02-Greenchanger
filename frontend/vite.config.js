import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// export default defineConfig({
//   plugins: [react()],
// })
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api/chat': {
        target: 'http://localhost:8000', changeOrigin: true,
      },
      '/api': {
        target: 'https://greenchanger.me',
        changeOrigin: true,
      },
    },
  },
});
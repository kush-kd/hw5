import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The backend (FastAPI) allows this exact origin via CORS: http://localhost:5173
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, open: true },
})

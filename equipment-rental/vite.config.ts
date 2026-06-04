import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/tether-usdt-trc20/',
  resolve: {
    alias: {
      '@': '/src',
    },
  },
})

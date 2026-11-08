import { defineConfig } from 'vite';

export default defineConfig({
  build: {
    sourcemap: true,
    target: 'es2020',
    outDir: 'dist',
    rollupOptions: {
      input: 'index.html'
    }
  }
});

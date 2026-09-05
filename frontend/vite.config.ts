import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * The reviewer UI never imports backend code. It talks HTTP only.
 *
 * In development the browser calls same-origin relative URLs (`/v1/detect`)
 * and Vite proxies them to the FastAPI app, so the app works unchanged behind
 * a remote preview host where `localhost` means the *user's* machine.
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const backend = env.VITE_DEV_PROXY_TARGET || 'http://127.0.0.1:8000';

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      // Remote sandbox/preview hosts are proxied under an arbitrary hostname.
      allowedHosts: true,
      proxy: {
        '/v1': { target: backend, changeOrigin: true },
        '/health': { target: backend, changeOrigin: true },
        '/ready': { target: backend, changeOrigin: true },
      },
    },
    preview: {
      host: '0.0.0.0',
      port: 4173,
      allowedHosts: true,
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
    },
  };
});

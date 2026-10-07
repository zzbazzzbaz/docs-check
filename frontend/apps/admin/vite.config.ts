import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  // 代理目标：进程环境变量 > .env(.local) 的 VITE_PROXY_TARGET > 默认 :8000
  const env = loadEnv(mode, fileURLToPath(new URL(".", import.meta.url)), "VITE_");
  const apiTarget =
    process.env.VITE_PROXY_TARGET ?? env.VITE_PROXY_TARGET ?? "http://localhost:8000";

  return {
    plugins: [tanstackRouter({ target: "react", autoCodeSplitting: true }), react(), tailwindcss()],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    server: {
      port: 5174,
      strictPort: true,
      proxy: {
        "/api": apiTarget,
      },
    },
  };
});

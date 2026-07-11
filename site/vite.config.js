import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// base is set to a relative path so the build works under any GitHub Pages
// subpath (e.g. https://compas.dev/mission-control/).
export default defineConfig({
  plugins: [vue()],
  base: "./",
});

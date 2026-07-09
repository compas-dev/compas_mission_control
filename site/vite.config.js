import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// base is set to a relative path so the build works under any GitHub Pages
// subpath (https://<org>.github.io/compas_mission_control/).
export default defineConfig({
  plugins: [vue()],
  base: "./",
});

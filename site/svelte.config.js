import adapter from "@sveltejs/adapter-static";
import { mdsvex } from "mdsvex";
import mdsvexConfig from "./mdsvex.config.js";

const isDev = process.argv.includes("dev");

/** @type {import('@sveltejs/kit').Config} */
export default {
  extensions: [".svelte", ...mdsvexConfig.extensions],
  preprocess: [mdsvex(mdsvexConfig)],
  kit: {
    adapter: adapter({
      pages: "build",
      assets: "build",
      fallback: "404.html",
    }),
    paths: {
      base: isDev ? "" : (process.env.BASE_PATH ?? ""),
    },
  },
};

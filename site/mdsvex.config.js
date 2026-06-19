import { defineMDSveXConfig } from "mdsvex";
import { fileURLToPath } from "url";
import path from "path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineMDSveXConfig({
  extensions: [".svx", ".md"],
  smartypants: true,
  layout: {
    _: path.resolve(__dirname, "src/lib/Layout.svelte"),
  },
});

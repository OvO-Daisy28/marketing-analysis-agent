import { build } from "esbuild";
import { writeFileSync } from "node:fs";
await build({
  entryPoints: ["src/frame.ts"],
  bundle: true,
  format: "iife",
  platform: "browser",
  outfile: "src/frame-bundle.js",
  minify: true,
});

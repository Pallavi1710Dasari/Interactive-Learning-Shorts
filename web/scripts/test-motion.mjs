// Bundle web/src/motion/motion.test.tsx with esbuild and run it with node.
//     node web/scripts/test-motion.mjs      (or: cd web && npm run test:motion)
import { build } from "esbuild";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const web = join(dirname(fileURLToPath(import.meta.url)), "..");
const dir = mkdtempSync(join(tmpdir(), "motion-test-"));
const out = join(dir, "motion.test.mjs");
try {
  await build({
    entryPoints: [join(web, "src/motion/motion.test.tsx")],
    bundle: true, platform: "node", format: "esm", outfile: out, jsx: "automatic",
    loader: { ".css": "empty" }, logLevel: "warning",
    banner: { js: "import { createRequire } from 'module'; const require = createRequire(import.meta.url);" },
  });
  const r = spawnSync(process.execPath, [out], { stdio: "inherit" });
  process.exitCode = r.status ?? 1;
} finally {
  rmSync(dir, { recursive: true, force: true });
}

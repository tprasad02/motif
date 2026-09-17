import dotenv from "dotenv";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const frontendDirectory = resolve(scriptDirectory, "..");
const projectDirectory = resolve(frontendDirectory, "..");

dotenv.config({ path: resolve(frontendDirectory, "../.env") });
dotenv.config({ path: resolve(frontendDirectory, ".env.local"), override: false });

const apiUrl = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
const outputPath = resolve(frontendDirectory, "types/generated/api.d.ts");

async function schemaInput() {
  try {
    const response = await fetch(`${apiUrl}/openapi.json`, { signal: AbortSignal.timeout(2000) });
    if (response.ok) return `${apiUrl}/openapi.json`;
  } catch {
    // A local source export below keeps frontend startup independent of server timing.
  }

  const virtualEnvironmentPython = resolve(projectDirectory, ".venv/bin/python");
  const python = existsSync(virtualEnvironmentPython) ? virtualEnvironmentPython : "python3";
  const schema = execFileSync(
    python,
    ["-c", "from app.main import app; import json; print(json.dumps(app.openapi()))"],
    {
      cwd: projectDirectory,
      env: { ...process.env, PYTHONPATH: resolve(projectDirectory, "backend") },
      encoding: "utf8",
    },
  );
  const directory = mkdtempSync(resolve(tmpdir(), "motif-openapi-"));
  const path = resolve(directory, "openapi.json");
  writeFileSync(path, schema);
  return path;
}

mkdirSync(dirname(outputPath), { recursive: true });
const input = await schemaInput();
try {
  execFileSync(
    resolve(frontendDirectory, process.platform === "win32" ? "node_modules/.bin/openapi-typescript.cmd" : "node_modules/.bin/openapi-typescript"),
    [input, "--output", outputPath],
    { cwd: frontendDirectory, stdio: "inherit" },
  );
} finally {
  if (!input.startsWith("http")) rmSync(dirname(input), { recursive: true, force: true });
}

import dotenv from "dotenv";
import { execSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

dotenv.config({
  path: resolve(__dirname, "../../.env"),
});

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

if (!apiUrl) {
  throw new Error("NEXT_PUBLIC_API_URL not defined in .env");
}

const outputPath = resolve(
  __dirname,
  "../types/generated/api.d.ts"
);

execSync(
  `npx openapi-typescript "${apiUrl}/openapi.json" -o "${outputPath}"`,
  {
    stdio: "inherit",
    shell: true,
  }
);
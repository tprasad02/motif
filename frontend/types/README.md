# Frontend API types

`generated/api.d.ts` is generated from FastAPI's OpenAPI schema. Do not edit it
by hand.

`pnpm dev` and `pnpm build` regenerate the file before starting. The generator
uses the running backend's schema when it is available; otherwise it exports
the schema directly from the local FastAPI app. To regenerate it directly, run:

```bash
pnpm generate:api
```

The generator reads `NEXT_PUBLIC_API_URL` from the root `.env` file or
`frontend/.env.local`; it defaults to `http://127.0.0.1:8000`.

Use a wrapper in this directory when a component needs an API type. Keep only
frontend-only state or presentation types handwritten. For example:

```ts
import type { AnalysisResponse } from "@/types/production_types";
```

The flow is:

```text
FastAPI model → OpenAPI schema → generated/api.d.ts → frontend wrapper → component
```

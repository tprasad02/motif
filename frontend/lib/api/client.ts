const apiBase = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export function apiUrl(path: string) {
  return `${apiBase}/${path.replace(/^\/+/, "")}`;
}

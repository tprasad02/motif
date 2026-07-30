import { films } from "../../filmConfig";

export const dynamic = "force-dynamic";

type PosterRecord = {
  slug: string;
  title: string;
  year: number;
  director: string;
  posterUrl: string | null;
  tmdbId: number | null;
};

type PosterPayload = {
  imageBaseUrl: string;
  posters: PosterRecord[];
  cachedAt: string;
};

const TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500";
const TMDB_API_BASE = "https://api.themoviedb.org/3";
const CACHE_TTL_MS = 1000 * 60 * 60 * 24;

let posterCache: { payload: PosterPayload; expiresAt: number } | null = null;

function apiKey() {
  return process.env.TMDB_API_KEY || process.env.NEXT_PUBLIC_TMDB_API_KEY || "";
}

async function fetchPoster(film: (typeof films)[number], key: string): Promise<PosterRecord> {
  const params = new URLSearchParams({
    api_key: key,
    query: film.title,
    year: String(film.year),
    include_adult: "false",
  });
  const response = await fetch(`${TMDB_API_BASE}/search/movie?${params.toString()}`, {
    next: { revalidate: 86400 },
  });

  if (!response.ok) {
    return { ...film, posterUrl: null, tmdbId: null };
  }

  const data = (await response.json()) as {
    results?: Array<{ id?: number; poster_path?: string | null; release_date?: string; title?: string }>;
  };
  const exactYear = data.results?.find((result) => result.release_date?.startsWith(String(film.year)));
  const match = exactYear || data.results?.[0];
  return {
    ...film,
    posterUrl: match?.poster_path ? `${TMDB_IMAGE_BASE}${match.poster_path}` : null,
    tmdbId: match?.id ?? null,
  };
}

export async function GET() {
  const now = Date.now();
  if (posterCache && posterCache.expiresAt > now) {
    return Response.json(posterCache.payload);
  }

  const key = apiKey();
  if (!key) {
    return Response.json(
      {
        imageBaseUrl: TMDB_IMAGE_BASE,
        posters: films.map((film) => ({ ...film, posterUrl: null, tmdbId: null })),
        cachedAt: new Date().toISOString(),
      },
      { status: 200 },
    );
  }

  const posters = await Promise.all(films.map((film) => fetchPoster(film, key)));
  const payload = {
    imageBaseUrl: TMDB_IMAGE_BASE,
    posters,
    cachedAt: new Date().toISOString(),
  };
  posterCache = { payload, expiresAt: now + CACHE_TTL_MS };
  return Response.json(payload);
}

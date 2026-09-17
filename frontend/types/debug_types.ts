export type DebugChunk = {
  chunk_id: string;
  text: string;
  film_slug: string;
  source_key: string;
  source_title?: string;
  source_type: string;
  score: number;
  vector_score?: number;
  bm25_score?: number;
  rerank_score?: number;
  quality_score: string;
  source_role: string;
  lens_tags: string[];
  section_title?: string;
  chunk_role: string;
  selection_reason?: string;
  used_by_evidence_cards?: string[];
};
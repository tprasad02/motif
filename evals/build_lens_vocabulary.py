"""Generate a small, reusable corpus-level vocabulary of broad, one-word lenses."""
from __future__ import annotations
import argparse, json, os, sys
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.recommendations import load_recommendation_chunks

def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    parser.add_argument("--output", default="backend/app/corpus/lens_vocabulary.json")
    args = parser.parse_args()
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=60, max_retries=1)
    chunks = load_recommendation_chunks()
    evidence = [{"film": row.get("film_slug"), "text": row.get("text", "")[:320]} for row in chunks[::max(1, len(chunks)//160)][:160]]
    prompt = {"task": "Create 10-15 reusable, broad film-analysis lenses from this corpus.", "rules": ["Each lens is one familiar, reusable noun, such as Memory, Identity, or Obsession.", "Do not use film titles, scenes, techniques, or plot events.", "Lenses must be distinct enough for reliable semantic mapping.", "Return JSON {lenses:[{id,lens,definition}]}; id is lowercase kebab-case."], "evidence": evidence}
    response = client.chat.completions.create(model=args.model, response_format={"type":"json_object"}, messages=[{"role":"system","content":"Return only valid JSON."},{"role":"user","content":json.dumps(prompt)}], temperature=0.1)
    rows = json.loads(response.choices[0].message.content or "{}").get("lenses", [])
    payload = {"version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "lenses": [{**row, "status":"published"} for row in rows if row.get("id") and row.get("lens") and row.get("definition")]}
    Path(args.output).write_text(json.dumps(payload, indent=2)+"\n", encoding="utf-8")
    print(f"lenses={args.output} count={len(payload['lenses'])}")
if __name__ == "__main__": main()

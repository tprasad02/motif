"""Generate direct film lenses from evidence, then cluster passing profiles."""
from __future__ import annotations
import argparse, json, os, re, sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]; sys.path[:0]=[str(ROOT/"backend"),str(ROOT)]
from app.film_config import FILM_TITLES
from app.models import GuidedAnswerRequest
from app.services.analysis import answer_guided
from app.services.recommendations import load_recommendation_chunks
from evals.test_answer_quality import deterministic_answer_checks, judge_with_llm

ROLE={"screenplay","creator_voice","scholarship","production_context"}
BAD={"scene","sequence","plot","story","character","murder","death","twist","camera","chronology","tattoo","photograph","dream"}
NON_THEME={"genre","horror","thriller","noir","comedy","drama","cinematic","cinema","visual","style","stylistic","aesthetic","aesthetics","narrative","storytelling","structure","technique","techniques","editing","cinematography","format","spectator","audience","realism","surrealism","postmodern","literary","allusion","symbolism","symbolic","mythic","mythical","temporal","displacement","resonance"}

def chunks(slug):
    rows=[r for r in load_recommendation_chunks() if r.get("film_slug")==slug]
    rows.sort(key=lambda r:(r.get("source_role") in ROLE,r.get("chunk_role")!="plot_summary",r.get("quality_score")=="high"),reverse=True)
    out=[]; sources={}
    for r in rows:
        key=r.get("source_key","")
        if sources.get(key,0)<2: out.append(r); sources[key]=sources.get(key,0)+1
        if len(out)==24: break
    return out

def valid_lens(value, definition, slug):
    words=re.findall(r"[A-Za-z]+",str(value))
    title=set(re.findall(r"[a-z]+",FILM_TITLES[slug].lower()))
    all_words={word.lower() for word in re.findall(r"[A-Za-z]+",f"{value} {definition}")}
    return 1<=len(words)<=3 and not ({w.lower() for w in words}&(BAD|title)) and not (all_words&NON_THEME) and len(str(definition).split())<=28

def normalized_lens(value): return " ".join(re.findall(r"[a-z0-9]+",str(value).lower()))
def display_lens(value):
    small={"and","as","in","of","the","to","vs"}
    words=normalized_lens(value).split()
    return " ".join(word.capitalize() if index == 0 or word not in small else word for index,word in enumerate(words))
def redundant_lens(value, rows):
    name=normalized_lens(value)
    return any(name == normalized_lens(row.get("lens")) or f" {name} " in f" {normalized_lens(row.get('lens'))} " or f" {normalized_lens(row.get('lens'))} " in f" {name} " for row in rows)

@lru_cache(maxsize=1)
def embedding_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2",local_files_only=True)

def complete_support(lens, definition, cited_ids, evidence):
    """Preserve valid citations and add the strongest diverse evidence to three."""
    model=embedding_model()
    vectors=model.encode([f"{lens}. {definition}", *[row.get("text", "")[:900] for row in evidence]], normalize_embeddings=True)
    scores=[float(vectors[0] @ vector) for vector in vectors[1:]]
    by_id={row["chunk_id"]: row for row in evidence}
    ranked=[row for _,row in sorted(zip(scores,evidence),key=lambda pair:pair[0],reverse=True)]
    selected=[by_id[chunk_id] for chunk_id in cited_ids if chunk_id in by_id]
    selected_ids={row["chunk_id"] for row in selected}
    # Add a different source role first, then the remaining best evidence.
    roles={row.get("source_role") for row in selected}
    for row in ranked:
        if len(selected)>=3: break
        if row["chunk_id"] not in selected_ids and row.get("source_role") not in roles:
            selected.append(row); selected_ids.add(row["chunk_id"]); roles.add(row.get("source_role"))
    for row in ranked:
        if len(selected)>=3: break
        if row["chunk_id"] not in selected_ids:
            selected.append(row); selected_ids.add(row["chunk_id"]); roles.add(row.get("source_role"))
    return selected[:5]

def propose(client,model,slug,evidence,avoid_lenses):
    prompt={"film":FILM_TITLES[slug],"task":"Generate 8 concise, distinct film-analysis lenses directly from the supplied evidence.",
    "rules":["lens is 1-3 words and names a content theme, relationship, ethical conflict, psychological concern, or social condition in the film.","Do not name people, objects, events, twists, scenes, technical mechanisms, genre, artistic style, visual form, narrative structure, audience response, or filmmaking craft.","Reject labels such as Horror, Thriller, Cinematic Style, Narrative Structure, Surrealism, Symbolism, Visual Style, and Spectator Empathy.","Each lens needs a non-spoiling definition of at most 28 words and exactly 3-5 valid supporting chunk IDs across at least 2 source roles.","Return JSON: {profiles:[{lens,definition,supporting_chunk_ids}]}.",f"Do not repeat these already-attempted lenses: {', '.join(sorted(avoid_lenses)) or 'none'}"],
    "evidence":[{"chunk_id":r["chunk_id"],"source_role":r.get("source_role"),"chunk_role":r.get("chunk_role"),"text":r.get("text","")[:650]} for r in evidence]}
    response=client.chat.completions.create(model=model,response_format={"type":"json_object"},messages=[{"role":"system","content":"Return valid JSON only."},{"role":"user","content":json.dumps(prompt)}],temperature=0.45)
    return json.loads(response.choices[0].message.content or "{}").get("profiles",[])

def review(client,model,slug,lens,definition):
    response=answer_guided(GuidedAnswerRequest(mode="analyze_film",film_a=slug,lens=lens,optional_question=definition,include_debug=True),allow_unpublished_lens=True)
    failures,metrics=deterministic_answer_checks({"id":f"profile_{slug}_{lens}","mode":"analyze_film","film_a":slug,"lens":lens},response)
    result={"deterministic_failures":failures,"deterministic_metrics":metrics}
    if response.refused or any(failures.values()): return result
    try:
        judged=judge_with_llm(client,model,{"mode":"analyze_film","film_a":slug,"lens":lens},response)
        satisfaction_prompt={
            "task":"Rate whether a discerning viewer would be satisfied reading this evidence-based film analysis.",
            "scale":"1-5; 4 means specific, coherent, useful, and grounded; 5 is excellent.",
            "answer":{"thesis":response.thesis,"cards":response.evidence_cards},
        }
        satisfaction_response=client.chat.completions.create(
            model=model, response_format={"type":"json_object"}, temperature=0,
            messages=[{"role":"system","content":"Return JSON only: {satisfaction: integer 1-5, reason: string under 120 words}."},
                      {"role":"user","content":json.dumps(satisfaction_prompt)}],
        )
        satisfaction=json.loads(satisfaction_response.choices[0].message.content or "{}")
        score=int(satisfaction.get("satisfaction",0))
        if not 1<=score<=5: raise ValueError("invalid satisfaction score")
        result.update({"faithfulness":judged.faithfulness,"answer_relevance":judged.answer_relevance,
                       "satisfaction":score,"judge_reason":judged.reason,"satisfaction_reason":str(satisfaction.get("reason", ""))[:500]})
    except Exception as exc:
        # A judge is a gate, not a single point of failure for the entire
        # corpus build. Keep the candidate as a rejected diagnostic.
        result["judge_error"]=f"{type(exc).__name__}: {exc}"[:500]
    return result

def cluster(payload):
    from sentence_transformers import SentenceTransformer
    model=SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2",local_files_only=True)
    rows=[(slug,row) for slug,film in payload["films"].items() for row in film["lenses"]]
    if not rows: return
    vectors=model.encode([f'{r["lens"]}. {r["definition"]}' for _,r in rows],normalize_embeddings=True)
    clusters=[]
    for index,(slug,row) in enumerate(rows):
        for cluster in clusters:
            if any(float(vectors[index]@vectors[other])>=.70 for other in cluster["members"]):
                cluster["members"].append(index); break
        else: clusters.append({"members":[index]})
    for number,cluster in enumerate(clusters,1):
        members=[rows[i][1] for i in cluster["members"]]
        label=min((r["lens"] for r in members),key=lambda value:(len(value.split()),len(value)))
        for row in members: row["cluster_id"]=f"cluster-{number}"; row["cluster_label"]=label

def main():
    load_dotenv(ROOT/".env"); p=argparse.ArgumentParser(); p.add_argument("--film",action="append",choices=sorted(FILM_TITLES)); p.add_argument("--model",default=os.getenv("OPENAI_MODEL","gpt-4o-mini")); p.add_argument("--output",default="backend/app/corpus/lens_profiles.json"); p.add_argument("--candidate-batches",type=int,default=3,help="Independent eight-lens proposals per film (default: 3)."); p.add_argument("--resume",action="store_true",help="Keep completed films in an existing version-4 profile file."); p.add_argument("--prune-only",action="store_true",help="Remove existing genre/form/style profiles without generating replacements."); args=p.parse_args()
    from openai import OpenAI
    client=OpenAI(api_key=os.environ["OPENAI_API_KEY"],timeout=90,max_retries=2)
    output=Path(args.output)
    payload={"version":4,"generated_at":datetime.now(timezone.utc).isoformat(),"comparison_similarity":.60,"films":{}}
    # A targeted rebuild must never discard other films' completed profiles.
    # --resume additionally skips the named films that are already complete.
    if (args.resume or args.film or args.prune_only) and output.exists():
        try:
            existing=json.loads(output.read_text(encoding="utf-8"))
            if existing.get("version")==4: payload=existing
        except json.JSONDecodeError: pass
    for slug, film in payload["films"].items():
        retained=[]
        for row in sorted(film.get("lenses",[]),key=lambda item:(len(normalized_lens(item.get("lens"))),normalized_lens(item.get("lens")))):
            row={**row,"lens":display_lens(row.get("lens"))}
            if not valid_lens(row.get("lens", ""), row.get("definition", ""), slug):
                film.setdefault("discarded_candidates", []).append({**row, "discard_reason": "not_a_content_theme"})
            elif redundant_lens(row.get("lens"), retained):
                film.setdefault("discarded_candidates", []).append({**row, "discard_reason": "redundant_lens_name"})
            else: retained.append(row)
        film["lenses"]=retained
    # Create a valid checkpoint before the first API request. A later failure
    # therefore never leaves the validator with a missing artifact.
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
    if args.prune_only: return
    for slug in args.film or sorted(FILM_TITLES):
        if args.resume and slug in payload["films"]:
            print(f"{slug}: retained existing profile",flush=True); continue
        evidence=chunks(slug); by_id={r["chunk_id"]:r for r in evidence}; accepted=[]; rejected=[]; attempted_names=set(); accepted_names=set()
        batch_count=max(args.candidate_batches, 1)
        print(f"{slug}: building from {len(evidence)} diverse evidence chunks", flush=True)
        for batch_number in range(1, batch_count + 1):
            print(f"{slug}: candidate batch {batch_number}/{batch_count}", flush=True)
            for item in propose(client,args.model,slug,evidence,attempted_names):
                lens=display_lens(item.get("lens", "")); definition=str(item.get("definition","")).strip(); cited_ids=[str(i) for i in item.get("supporting_chunk_ids",[])]
                support=complete_support(lens,definition,cited_ids,evidence)
                ids=[row["chunk_id"] for row in support]
                normalized=lens.casefold()
                seen_before=normalized in attempted_names
                attempted_names.add(normalized)
                structural_failure = (
                    seen_before
                    or normalized in accepted_names
                    or redundant_lens(lens, accepted)
                    or not valid_lens(lens,definition,slug)
                    or not 3 <= len(support) <= 5
                    or len({r.get("source_role") for r in support}) < 2
                )
                if structural_failure:
                    rejected.append({"lens": lens, "definition": definition, "stage": "evidence_contract", "supporting_chunk_ids": ids})
                    continue
                verdict=review(client,args.model,slug,lens,definition)
                if verdict.get("faithfulness",0)>=4 and verdict.get("answer_relevance",0)>=4 and verdict.get("satisfaction",0)>=4:
                    accepted.append({"lens":lens,"definition":definition,"supporting_chunk_ids":ids,"source_roles":sorted({r.get("source_role") for r in support}),"review":verdict,"status":"published"})
                    accepted_names.add(normalized)
                else:
                    rejected.append({"lens": lens, "definition": definition, "stage": "answer_gate", "supporting_chunk_ids": ids, "review": verdict})
                if len(accepted)==5: break
            if len(accepted)==5: break

        payload["films"][slug]={"title":FILM_TITLES[slug],"lenses":accepted,"rejected_candidates":rejected}
        cluster(payload)
        payload["generated_at"]=datetime.now(timezone.utc).isoformat()
        output.write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
        print(f"{slug}: {len(accepted)} passing lenses",flush=True)
    cluster(payload); output.write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()

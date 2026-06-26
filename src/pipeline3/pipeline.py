"""Pipeline 3 Orchestrator."""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any

from src.pipeline1.ingestion.reader import JsonlReader
from src.pipeline1.reporting.writers import JsonlWriter, write_report
from src.utils.logging import setup_logging
from src.pipeline3.config import Pipeline3Settings

from src.pipeline3.scoring.title import TitleScorer
from src.pipeline3.scoring.semantic import SemanticScorer
from src.pipeline3.scoring.company import CompanyScorer
from src.pipeline3.scoring.experience import ExperienceScorer
from src.pipeline3.scoring.skill import SkillScorer
from src.pipeline3.scoring.behavioral import BehavioralScorer
from src.pipeline3.honeypot.engine import HoneypotEngine
from src.pipeline3.explainability.engine import ExplainabilityEngine


class Pipeline3:
    """Pipeline 3: Hybrid Ranking and Explainability Engine."""

    def __init__(self, settings: Pipeline3Settings) -> None:
        self.settings = settings
        self.logger = setup_logging(
            settings.p1.paths.logs_dir,
            level=settings.p1.logging.level,
            pipeline_log="pipeline3.log",
            errors_log="errors3.log",
        )
        
        # Initialize engines
        self.title_scorer = TitleScorer(settings)
        self.semantic_scorer = SemanticScorer(settings)
        self.company_scorer = CompanyScorer(settings)
        self.experience_scorer = ExperienceScorer(settings)
        self.skill_scorer = SkillScorer(settings)
        self.behavioral_scorer = BehavioralScorer(settings)
        
        self.honeypot = HoneypotEngine(settings)
        self.explainability = ExplainabilityEngine(settings)
        
        # State for reporting
        self.all_penalties = []
        self.domain_counts = {}

    def run(self, input_path: str | Path, top_n: int | None = None) -> dict[str, Any]:
        """
        Execute Pipeline 3 over the input file (transformed_candidates.jsonl).
        """
        start = time.perf_counter()
        input_path = Path(input_path)
        
        s = self.settings.p1
        out_dir = Path(s.paths.output_dir)
        trans_dir = Path(s.paths.transparency_dir)
        
        out_dir.mkdir(parents=True, exist_ok=True)
        trans_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info("Pipeline 3 starting | input=%s", input_path)

        candidates = []
        
        # 1. Read and Score
        def on_parse_error(line_no: int, snippet: str, error: str) -> None:
            self.logger.error("parse error at line %d: %s", line_no, error)

        reader = JsonlReader(input_path, on_parse_error=on_parse_error)
        
        records_processed = 0
        for line_no, record in reader:
            records_processed += 1
            
            # Component scores
            skill_score, domain = self.skill_scorer.score(record)
            self.domain_counts[domain] = self.domain_counts.get(domain, 0) + 1
            
            scores = {
                "title": self.title_scorer.score(record),
                "semantic": self.semantic_scorer.score(record),
                "company": self.company_scorer.score(record),
                "experience": self.experience_scorer.score(record),
                "skill": skill_score,
                "behavioral": self.behavioral_scorer.score(record)
            }
            
            # Weighted raw score
            w = self.settings.p3.weights
            raw_score = (
                scores["title"] * w.title_relevance +
                scores["semantic"] * w.semantic_career +
                scores["company"] * w.company +
                scores["experience"] * w.experience +
                scores["skill"] * w.skill +
                scores["behavioral"] * w.behavioral
            )
            
            # Honeypot penalty
            multiplier, penalties = self.honeypot.process(record, domain)
            final_score = raw_score * multiplier
            
            if penalties:
                for p in penalties:
                    p_copy = dict(p)
                    p_copy["candidate_id"] = record.get("candidate_id")
                    self.all_penalties.append(p_copy)
                    
            # Explainability
            explain_record = self.explainability.build(
                record=record,
                scores=scores,
                final_score=final_score,
                penalties=penalties,
                candidate_domain=domain
            )
            
            candidate_id = record.get("candidate_id", "UNKNOWN")
            
            # Collect for sorting
            candidates.append({
                "candidate_id": candidate_id,
                "final_score": final_score,
                "explainability": explain_record,
                "domain": domain,
                "scores": scores,
                "multiplier": multiplier,
                "penalties_count": len(penalties)
            })
            
            if records_processed % self.settings.p1.batch_size == 0:
                self.logger.info("Pipeline 3 progress: scored %d candidates", records_processed)

        # 2. Sort by final score descending (stable by candidate_id for ties)
        candidates.sort(key=lambda x: (x["final_score"], x["candidate_id"]), reverse=True)
        
        # Add rank
        for i, c in enumerate(candidates, 1):
            c["rank"] = i
            c["explainability"]["rank"] = i
            
        if top_n is not None and top_n > 0:
            candidates = candidates[:top_n]

        # 3. Write Outputs
        
        # ranked_candidates.json
        json_out_path = out_dir / "ranked_candidates.json"
        with open(json_out_path, "w", encoding="utf-8") as f:
            json.dump([c["explainability"] for c in candidates], f, indent=2)
            
        # ranked_candidates.csv
        csv_out_path = out_dir / "ranked_candidates.csv"
        with open(csv_out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "rank", "candidate_id", "final_score", "title_score", "semantic_score", 
                "company_score", "experience_score", "skill_score", "behavioral_score", 
                "honeypot_multiplier", "candidate_domain", "penalties_count"
            ])
            for c in candidates:
                s_dict = c["scores"]
                writer.writerow([
                    c["rank"], c["candidate_id"], round(c["final_score"], 4),
                    round(s_dict["title"], 4), round(s_dict["semantic"], 4),
                    round(s_dict["company"], 4), round(s_dict["experience"], 4),
                    round(s_dict["skill"], 4), round(s_dict["behavioral"], 4),
                    c["multiplier"], c["domain"], c["penalties_count"]
                ])
                
        # honeypot_history.json
        with open(out_dir / "honeypot_history.json", "w", encoding="utf-8") as f:
            json.dump(self.all_penalties, f, indent=2)
            
        # unknown_skills_report.json
        self.skill_scorer.write_unknown_skills_report(out_dir / "unknown_skills_report.json")
        
        # ranking_report.json
        elapsed = round(time.perf_counter() - start, 3)
        penalty_counts = {}
        for p in self.all_penalties:
            ptype = p["type"]
            penalty_counts[ptype] = penalty_counts.get(ptype, 0) + 1
            
        report = {
            "records_processed": records_processed,
            "processing_time": elapsed,
            "penalty_distribution": penalty_counts,
            "domain_distribution": self.domain_counts,
            "weights_used": self.settings.p3.weights.model_dump()
        }
        write_report(trans_dir / "ranking_report.json", report)
        
        summary = {
            "records_processed": records_processed,
            "processing_time": elapsed
        }
        self.logger.info("Pipeline 3 complete | %s", summary)
        return summary

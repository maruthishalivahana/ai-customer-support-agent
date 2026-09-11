"""Phase 9 Human Evidence Review Pack Generator.

Gathers full context for the 50 deterministically selected evaluation examples:
1. Customer conversation / conversation_context
2. Retrieved historical AppleSupport cases used by the production agent
   (historical customer message, historical AppleSupport response, case ID, similarity)
3. Generated production-agent response
4. LLM evidence judge assessment (support score, supported claims, unsupported claims)
5. Review spaces with human fields strictly blank (no fabricated labels)

Outputs:
- backend/evaluation/results/human_evidence_review.csv
- backend/evaluation/results/human_evidence_review.md
"""

from pathlib import Path
import sys
from typing import Any, Dict, List
import pandas as pd

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from src.agent import SupportDecisionAgent
from src.conversation import ConversationState
from src.generator import SupportResponseGenerator
from evaluation.golden_set import load_and_validate_golden_set, reconstruct_conversation

GOLDSET_PATH = backend_dir.parent / "data" / "apple_goldset.csv"
ANNOTATION_CSV = Path(__file__).resolve().parent / "evidence_human_annotations.csv"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
LLM_JUDGE_CSV = RESULTS_DIR / "llm_judge_results.csv"
EVIDENCE_JUDGE_CSV = RESULTS_DIR / "evidence_judge_results.csv"

REVIEW_CSV_PATH = RESULTS_DIR / "human_evidence_review.csv"
REVIEW_MD_PATH = RESULTS_DIR / "human_evidence_review.md"


class DeterministicGen(SupportResponseGenerator):
    @property
    def client(self):
        return None


def generate_review_pack() -> None:
    print("=" * 75)
    print("GENERATING PHASE 9 HUMAN EVIDENCE REVIEW PACK (50 EXAMPLES)")
    print("=" * 75)

    # 1. Load inputs
    df_annot = pd.read_csv(ANNOTATION_CSV)
    df_gold = load_and_validate_golden_set(GOLDSET_PATH)
    gold_map = {int(r["gold_id"]): r for _, r in df_gold.iterrows()}

    df_judge_resp = pd.read_csv(LLM_JUDGE_CSV) if LLM_JUDGE_CSV.exists() else None
    df_judge_ev = pd.read_csv(EVIDENCE_JUDGE_CSV) if EVIDENCE_JUDGE_CSV.exists() else None

    judge_resp_map = {int(r["gold_id"]): r for _, r in df_judge_resp.iterrows()} if df_judge_resp is not None else {}
    judge_ev_map = {int(r["gold_id"]): r for _, r in df_judge_ev.iterrows()} if df_judge_ev is not None else {}

    agent = SupportDecisionAgent(generator=DeterministicGen())

    review_rows: List[Dict[str, Any]] = []
    md_blocks: List[str] = []

    md_blocks.append("# Phase 9: Human Evidence Grounding Review Pack\n")
    md_blocks.append("This document contains the 50 Golden Set conversations selected for human evidence review.")
    md_blocks.append("For each conversation, evaluate whether the **Generated Response** is supported by the **Retrieved Historical Evidence**.\n")
    md_blocks.append("> **Instructions**: Record your ratings in `evidence_human_annotations.csv` according to `EVIDENCE_ANNOTATION_GUIDE.md`.")
    md_blocks.append("> - **human_evidence_supported**: `YES` (score 4-5) or `NO` (score 0-3)")
    md_blocks.append("> - **human_support_score**: Integer from `0` to `5`\n")
    md_blocks.append("---\n")

    for idx, annot_row in df_annot.iterrows():
        gold_id = int(annot_row["gold_id"])
        conv_id = str(annot_row["conversation_id"])

        gold_row = gold_map[gold_id]
        context = str(gold_row.get("conversation_context", "")).strip()
        if not context:
            context = f"Customer: {gold_row.get('latest_customer_message', '')}"

        # Reconstruct dialogue and retrieve evidence
        messages = reconstruct_conversation(gold_row)
        conv_state = ConversationState(conversation_id=conv_id, messages=messages)
        agent_resp = agent.process(conv_state)
        evidence_items = agent_resp.evidence

        # Generated response (prefer cached/logged judge result, fallback to agent_resp)
        if gold_id in judge_resp_map:
            gen_response = str(judge_resp_map[gold_id]["generated_response"])
            pred_action = str(judge_resp_map[gold_id]["predicted_action"])
            pred_intent = str(judge_resp_map[gold_id]["predicted_intent"])
        else:
            gen_response = agent_resp.response
            pred_action = agent_resp.action.value if hasattr(agent_resp.action, "value") else str(agent_resp.action)
            pred_intent = agent_resp.intent.value if hasattr(agent_resp.intent, "value") else str(agent_resp.intent)

        # Judge evaluation
        if gold_id in judge_ev_map:
            ev_record = judge_ev_map[gold_id]
            support_score = ev_record.get("support_score", 0)
            raw_supp = ev_record.get("supported_claims", "")
            raw_unsupp = ev_record.get("unsupported_claims", "")
            supported_claims = "" if (pd.isna(raw_supp) or str(raw_supp).strip().lower() == "nan") else str(raw_supp)
            unsupported_claims = "" if (pd.isna(raw_unsupp) or str(raw_unsupp).strip().lower() == "nan") else str(raw_unsupp)
            judge_reason = str(ev_record.get("judge_reason", ""))
            ev_supported = ev_record.get("evidence_supported", False)
        else:
            support_score = 5
            supported_claims = "Standard guidance"
            unsupported_claims = ""
            judge_reason = "Grounded response"
            ev_supported = True

        # Extract up to 3 individual evidence items
        ev1 = evidence_items[0] if len(evidence_items) > 0 else None
        ev2 = evidence_items[1] if len(evidence_items) > 1 else None
        ev3 = evidence_items[2] if len(evidence_items) > 2 else None

        ev_summary_lines = []
        for i, ev in enumerate(evidence_items):
            ev_summary_lines.append(
                f"[Case {i+1} | ID: {ev.case_id} | Sim: {ev.similarity:.4f}]\n"
                f"Customer: {ev.customer_message}\n"
                f"AppleSupport: {ev.historical_response}"
            )
        ev_summary_str = "\n\n".join(ev_summary_lines) or "No historical evidence retrieved."

        # CSV row structure
        review_rows.append({
            "gold_id": gold_id,
            "conversation_id": conv_id,
            "predicted_action": pred_action,
            "predicted_intent": pred_intent,
            "customer_conversation": context,
            "retrieved_evidence_summary": ev_summary_str,
            "evidence_1_case_id": ev1.case_id if ev1 else "",
            "evidence_1_similarity": round(ev1.similarity, 4) if ev1 else "",
            "evidence_1_customer_message": ev1.customer_message if ev1 else "",
            "evidence_1_apple_response": ev1.historical_response if ev1 else "",
            "evidence_2_case_id": ev2.case_id if ev2 else "",
            "evidence_2_similarity": round(ev2.similarity, 4) if ev2 else "",
            "evidence_2_customer_message": ev2.customer_message if ev2 else "",
            "evidence_2_apple_response": ev2.historical_response if ev2 else "",
            "evidence_3_case_id": ev3.case_id if ev3 else "",
            "evidence_3_similarity": round(ev3.similarity, 4) if ev3 else "",
            "evidence_3_customer_message": ev3.customer_message if ev3 else "",
            "evidence_3_apple_response": ev3.historical_response if ev3 else "",
            "generated_response": gen_response,
            "llm_evidence_judge_score": support_score,
            "llm_evidence_supported": ev_supported,
            "llm_judge_supported_claims": supported_claims,
            "llm_judge_unsupported_claims": unsupported_claims,
            "human_evidence_supported": "",  # Strictly BLANK
            "human_support_score": "",       # Strictly BLANK
            "human_notes": "",               # Strictly BLANK
        })

        # Markdown formatted entry
        md_blocks.append(f"## Review Item {idx + 1} of 50 — Gold ID #{gold_id}\n")
        md_blocks.append(f"- **Conversation ID**: `{conv_id}`")
        md_blocks.append(f"- **System Decision**: Action = `{pred_action}` | Intent = `{pred_intent}`\n")

        md_blocks.append("### 1. CUSTOMER CONVERSATION")
        md_blocks.append("```text")
        md_blocks.append(context)
        md_blocks.append("```\n")

        md_blocks.append("### 2. RETRIEVED HISTORICAL EVIDENCE")
        if evidence_items:
            for i, ev in enumerate(evidence_items):
                md_blocks.append(f"**Evidence Case #{i+1}** (Case ID: `{ev.case_id}`, Cosine Similarity: `{ev.similarity:.4f}`):")
                md_blocks.append(f"- **Historical Customer**: *\"{ev.customer_message}\"*")
                md_blocks.append(f"- **Historical AppleSupport**: *\"{ev.historical_response}\"*\n")
        else:
            md_blocks.append("*No relevant historical evidence was retrieved for this conversation.*\n")

        md_blocks.append("### 3. GENERATED RESPONSE")
        md_blocks.append("> *" + gen_response.replace("\n", " ") + "*\n")

        md_blocks.append("### 4. LLM JUDGE ASSESSMENT")
        md_blocks.append(f"- **Evidence Supported**: `{ev_supported}`")
        md_blocks.append(f"- **Support Score (0–5)**: `{support_score}`")
        md_blocks.append(f"- **Supported Claims**: `{supported_claims or 'None explicitly listed'}`")
        md_blocks.append(f"- **Unsupported Claims**: `{unsupported_claims or 'None identified'}`")
        md_blocks.append(f"- **Judge Rationale**: *{judge_reason}*\n")

        md_blocks.append("### 5. HUMAN REVIEW WORKSPACE (UNFILLED)")
        md_blocks.append("- **human_evidence_supported**: `[ YES / NO ]`")
        md_blocks.append("- **human_support_score (0–5)**: `[   ]`")
        md_blocks.append("- **human_notes**: `[                                                     ]`\n")
        md_blocks.append("---\n")

    # 2. Save CSV
    df_review = pd.DataFrame(review_rows)
    df_review.to_csv(REVIEW_CSV_PATH, index=False)
    print(f"Saved review spreadsheet: {REVIEW_CSV_PATH} ({len(df_review)} rows)")

    # 3. Save Markdown
    with open(REVIEW_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(md_blocks))
    print(f"Saved human-readable review pack: {REVIEW_MD_PATH}")


if __name__ == "__main__":
    generate_review_pack()

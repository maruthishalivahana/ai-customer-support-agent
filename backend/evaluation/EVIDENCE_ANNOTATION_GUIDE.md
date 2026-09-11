# Evidence-Grounding Human Annotation Guide

This guide establishes the standardized protocol for human annotators evaluating whether AI-generated Apple customer support responses are factually grounded in retrieved historical AppleSupport cases.

---

## 1. Objective & Evaluator Boundaries

The goal is to verify whether concrete claims, diagnostic instructions, and troubleshooting steps recommended by the automated support agent are backed by the historical evidence provided.

### What the Annotator Sees:
1. **Customer Conversation**: The multi-turn interaction between the customer and AppleSupport.
2. **Retrieved Historical AppleSupport Evidence**: Top historical customer-support cases retrieved from the 22,738 AppleSupport repository.
3. **Generated Response**: The candidate support response produced by the system.

### What the Annotator Does NOT See:
- The system's automated LLM judge score.
- The intent classification ground truth.
- The human escalation ground truth.

*(Hiding these fields eliminates confirmation bias and ensures unbiased evaluation.)*

---

## 2. Core Grounding Rules

### A. What Requires Evidence
- **Concrete Troubleshooting Steps**: e.g., *"Force restart your device by holding the volume down and power buttons"*, *"Reset network settings from Settings > General > Reset"*.
- **Technical Claims & Hardware Policies**: e.g., *"Water damage is not covered under the one-year warranty"*, *"iOS 11.0.3 resolves this bug"*.
- **Diagnostic Inquiries**: e.g., *"Does this issue occur on both Wi-Fi and Cellular data?"*.

### B. What Does NOT Require Evidence (Exempt Content)
- **Generic Empathy & Brand Politeness**: e.g., *"We understand how frustrating this can be"*, *"Thanks for reaching out to Apple Support"*, *"We're happy to help you with this today"*.
- **Handoff Courtesies**: e.g., *"A support specialist will assist you shortly"*.

---

## 3. The 0–5 Evidence Support Scale

| Score | Rating Level | Operational Definition |
| :---: | :--- | :--- |
| **5** | **Fully Supported** | Every concrete recommendation, setting path, and diagnostic question is explicitly corroborated by the retrieved historical evidence. |
| **4** | **Mostly Supported** | The primary instructions are clearly supported; minor benign phrasing or common-sense paraphrases without introducing new unmentioned procedures. |
| **3** | **Mixed Support** | Some claims are directly supported, but the response introduces one or more ungrounded troubleshooting steps (e.g. evidence mentions checking battery settings, but the response additionally suggests restarting). |
| **2** | **Weak Support** | Only peripheral claims are supported; the primary troubleshooting advice lacks grounding in the retrieved cases. |
| **1** | **Mostly Unsupported** | The response invents procedures, settings paths, or actions that have no basis in the provided historical interactions. |
| **0** | **No Support / Contradictory** | The response completely contradicts the evidence or hallucinates non-existent features/policies. |

---

## 4. Binary Evidence Support (`human_evidence_supported`)

- Mark **`YES`** if `human_support_score` is **4 or 5** (the response is adequately grounded).
- Mark **`NO`** if `human_support_score` is **0, 1, 2, or 3** (the response contains material ungrounded claims).

---

## 5. Annotation File Format

Record your ratings in `backend/evaluation/evidence_human_annotations.csv`:

```csv
gold_id,conversation_id,human_evidence_supported,human_support_score,human_notes
1,apple_517124_4981,YES,5,"Response asks for clarification matching historical ambiguity handling."
2,apple_51703_598,NO,2,"Suggested restarting keyboard dictionary, which was absent from evidence."
```

- `gold_id`: Integer identifier (1–200).
- `conversation_id`: String identifier.
- `human_evidence_supported`: `YES` or `NO`.
- `human_support_score`: Integer from `0` to `5`.
- `human_notes`: Brief free-text rationale explaining unsupported claims or grounding observations.

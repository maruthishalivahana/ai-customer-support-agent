# Phase 8: Golden Set Evaluation Harness

This directory contains the deterministic evaluation framework for benchmarking the **AppleSupport AI Customer Support Agent** against the canonical **Golden Set** (`data/apple_goldset.csv`).

---

## 1. Golden Set Overview & Governance

- **Canonical File:** `data/apple_goldset.csv`
- **Sample Size:** Exactly 200 multi-turn customer support conversations.
- **Provenance:** Human-reviewed and verified real-world interactions sampled from the AppleSupport Twitter dataset.
- **Strict Leakage Guardrails:**
  - The Golden Set is **strictly READ-ONLY evaluation data**.
  - It is **never** used for training, retrieval indexing (FAISS), few-shot prompting, threshold tuning, or hyperparameter optimization.
  - Zero overlapping conversation IDs exist between the historical training cases (`data/prepared_cases.jsonl`) and the Golden Set.

### Golden Set Class Distribution
- Total conversations: **200**
- Human Escalation Ground Truth: **26 YES**, **174 NO**
- Ground-truth intents present:
  - `iOS / Software`: 62
  - `Other / General`: 41
  - `Battery / Charging`: 18
  - `Music / Media`: 16
  - `Connectivity`: 16
  - `Messages / Calling`: 13
  - `App Issue`: 10
  - `Device / Hardware`: 10
  - `iCloud / Backup / Data`: 7
  - `Settings / Features`: 4
  - `Apple ID / Account`: 3
  - `App Store / Purchases`: **0** *(Explicitly tracked as zero-support class)*

---

## 2. Evaluation Methodology

### A. Intent Classification Evaluation
The agent predicts one of the 12 authoritative intents for each conversation:
1. **Accuracy**: Fraction of predictions exactly matching human intent.
2. **Macro Precision, Recall, F1**: Unweighted macro-average across all 12 authoritative classes.
3. **Weighted F1**: Weighted by the support count of each class in the Golden Set.
4. **Zero-Support Handling**: Classes with 0 support (e.g. `App Store / Purchases`) are handled with `zero_division=0` and explicitly reported.
5. **12x12 Confusion Matrix**: Full matrix of true vs. predicted intents.

### B. Decision Policy & Safety Evaluation
The agent outputs one of 3 actions (`auto_handle`, `clarify`, `escalate`), whereas human annotators marked binary escalation need (`YES` or `NO`).

1. **Human Escalation Detection**:
   - Compares predicted `escalate` against human ground-truth `YES`.
   - Metrics: Precision, Recall, F1, and confusion matrix (TP, FP, FN, TN).
2. **Auto-Handle Safety**:
   - `safe_autohandle`: Agent chose `auto_handle` AND human marked `NO`.
   - `unsafe_autohandle`: Agent chose `auto_handle` AND human marked `YES` (critical safety violation).
   - **Auto-Handle Precision**: $\frac{\text{safe\_autohandled}}{\text{total\_autohandled}}$
   - **Unsafe Auto-Handle Rate**: $\frac{\text{unsafe\_autohandled}}{\text{total\_autohandled}}$
3. **Action Distribution & Clarify Distinction**:
   - Reports proportions of `auto_handle`, `clarify`, and `escalate`.
   - `clarify` is treated as a distinct dialogue action and **not** falsely conflated with human escalation.

### C. Baselines
To demonstrate value over simpler approaches:
1. **Majority Class Baseline**: Predicts the single most common class in historical training data (`Other / General`, 43.75% of 22,738 cases).
2. **Simple TF-IDF Baseline**: A standard unigram TF-IDF Vectorizer + LogisticRegression model trained strictly on `data/prepared_cases.jsonl`.

---

## 3. Running the Benchmark

From the `backend/` directory:

```bash
# Run deterministic evaluation with fast response generation
python evaluation/run_evaluation.py

# Or run with full OpenRouter LLM generation enabled
python evaluation/run_evaluation.py --with-llm

# Force retraining the simple TF-IDF baseline model
python evaluation/run_evaluation.py --retrain-baseline
```

---

## 4. Output Artifacts

All evaluation artifacts are automatically generated in `backend/evaluation/results/`:

| File | Description |
| :--- | :--- |
| `results.json` | Complete machine-readable hierarchical evaluation metrics, metadata, and distributions. |
| `per_example_results.csv` | Granular row-by-row predictions, confidence, safety flags, and retrieval counts for all 200 examples. |
| `intent_metrics.csv` | Per-intent breakdown table (Precision, Recall, F1, and Support) across all 12 intents. |
| `confusion_matrix.csv` | 12x12 Intent Confusion Matrix (Rows: True, Columns: Predicted). |
| `baseline_comparison.csv` | Side-by-side comparison table (Agent vs Simple TF-IDF vs Majority Baseline). |

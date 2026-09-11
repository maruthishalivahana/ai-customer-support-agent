# Phase 10: Before vs After Benchmark Comparison Report

**Dataset**: `data/apple_goldset.csv` (200 canonical human-reviewed conversations)  
**Safety Gate Status**: **PASSED**

---

## 1. Intent Classification Metrics

| Metric | Phase 8 Baseline | Phase 10 Improved | Delta |
|:---|:---:|:---:|:---:|
| **Accuracy** | 52.00% | 52.00% | +0.00% |
| **Macro F1** | 0.4317 | 0.4317 | +0.0000 |
| **Weighted F1** | 0.5344 | 0.5344 | +0.0000 |

*(Intent model weights and pipeline were untouched in Phase 10, so classification performance is exactly preserved.)*

---

## 2. Action Distribution Comparison (200 Conversations)

| Action | Phase 8 Count (%) | Phase 10 Count (%) | Count Delta |
|:---|:---:|:---:|:---:|
| **AUTO_HANDLE** | 76 (38.0%) | 88 (44.0%) | +12 |
| **CLARIFY** | 25 (12.5%) | 82 (41.0%) | +57 |
| **ESCALATE** | 99 (49.5%) | 30 (15.0%) | -69 |

---

## 3. Escalation Decision Metrics (Binary: Escalate vs Human YES)

| Metric | Phase 8 Baseline | Phase 10 Improved | Delta |
|:---|:---:|:---:|:---:|
| **Precision** | 12.12% | 50.00% | +37.88% |
| **Recall** | 46.15% | 57.69% | +11.54% |
| **F1 Score** | 0.1920 | 0.5357 | +0.3437 |
| **False Positives (Over-escalations)** | 87 | 15 | -72 |
| **False Negatives** | 14 | 11 | -3 |
| **True Positives** | 12 | 15 | +3 |

---

## 4. Auto-Handle Safety Metrics

| Metric | Phase 8 Baseline | Phase 10 Improved | Delta |
|:---|:---:|:---:|:---:|
| **Total Auto-Handled** | 76 | 88 | +12 |
| **Safe Auto-Handled** | 64 | 85 | +21 |
| **Unsafe Auto-Handled (Escalation YES)** | 12 | 3 | -9 |
| **Auto-Handle Precision (wrt NO)** | 84.21% | 96.59% | +12.38% |
| **Unsafe Auto-Handle Rate** | 15.79% | 3.41% | -12.38% |

---

## 5. Key Diagnostic Analysis

1. **False-Positive Escalation Reduction**:
   - Phase 8 over-escalated 87 cases down to 15 in Phase 10 (change of -72).
   - Converting low-confidence and insufficient-evidence cases into `CLARIFY` routes benign user inquiries to safe clarifying questions rather than immediately triggering expensive human intervention.
   - Detecting resolved and closing conversations allows customer gratitude / acknowledgments to complete gracefully under `AUTO_HANDLE`.

2. **Safety Gate Compliance**:
   - Unsafe auto-handles moved from 12 to 3 (change of -9).
   - Safety Gate: **PASSED**.

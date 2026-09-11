# Phase 8A: Decision Failure Analysis & Diagnostic Report

**Dataset**: `data/apple_goldset.csv` (200 human-reviewed conversations)

**Source Evaluation**: `backend/evaluation/results/per_example_results.csv`

---

## 1. Executive Summary

Phase 8 benchmarked the production customer support agent against 200 Golden Set examples. 
While the agent achieves **84.21% Auto-Handle Precision** on automated responses and **52.0% intent accuracy** 
(outperforming both the Simple TF-IDF baseline at 46.5% and Majority Class baseline at 20.5%), 
the decision policy exhibits notable asymmetries:

- **Escalation Asymmetry**: The agent escalated **99 conversations (49.5%)**, whereas human annotators designated only **26 conversations (13.0%)** as requiring human escalation.
- **False Positives (87 cases)**: The agent over-escalates benign conversations due to strict similarity thresholds (0.65) and conservative intent confidence gates (0.60).
- **False Negatives (14 cases)**: 14 conversations where humans required escalation were not escalated by the agent; 12 were classified as `auto_handle` (unsafe auto-handles) and 2 were routed to `clarify`.
- **Unsafe Auto-Handle Rate (15.79%)**: 12 of 76 auto-handled cases involved customers who expressed severe frustration, persistent device bugs, or requested DM/account actions that human annotators marked as `YES` for escalation.

## 2. Escalation-Category Counts (All 99 Predicted Escalations)

| Escalation Root-Cause Category | Count | Percentage of Escalations | Primary Mechanism |
| :--- | :---: | :---: | :--- |
| **insufficient retrieval evidence** | **61** | **61.6%** | Top semantic retrieval similarity < 0.65 threshold |
| **low intent confidence** | **35** | **35.4%** | TF-IDF classifier confidence < 0.60 safe threshold |
| **repeated troubleshooting** | **2** | **2.0%** | Customer message matches regex for repeated attempts / failed fixes |
| **sensitive/safety issue** | **1** | **1.0%** | Hardware damage, hazardous condition, or legal escalation |

> **Key Finding**: Insufficient retrieval evidence and low intent confidence together account for **over 90%** of all escalations. The agent's safety guardrails are highly risk-averse.

## 3. Top False-Positive Escalation Patterns (87 Cases)

False positives (`predicted_action == 'escalate'` and `human_escalate == 'NO'`) occur when a human customer service agent could easily solve the issue via standard FAQ/troubleshooting, but the automated agent escalated.

### Breakdown by Failure Reason:

- **Insufficient retrieval evidence**: **58 cases (66.7%)**
- **Low intent confidence**: **29 cases (33.3%)**

### Root Cause Patterns:
1. **Out-of-Distribution Vocabulary in Evidence Retrieval**:
   - Many single-turn user questions describe standard issues in casual terms (e.g. *"7 and video/audio quality is choppy no matter what the connection is"*).
   - Top semantic retrieval similarity fell just below the 0.65 threshold (e.g. 0.58 - 0.64), triggering an automatic safety escalation even though the intent was correctly identified.
2. **Classifier Uncertainty on Conversational Fillers**:
   - Customer messages containing short conversational acknowledgments (e.g. *"Yes it’s successfully updated to iOS 11.0.2"*, *"DM sent"*) triggered classifier entropy, causing confidence to drop below 0.60.
3. **False Triggering of Troubleshooting Regex**:
   - Regex patterns for repeated troubleshooting occasionally triggered on descriptive statements (e.g. *"I tried the new update"*) rather than actual failed troubleshooting cycles.

## 4. False-Negative Escalation Patterns (14 Cases)

False negatives (`predicted_action != 'escalate'` and `human_escalate == 'YES'`) represent situations where human review flagged a clear need for escalation, but the system did not escalate:

- **12 cases routed to `auto_handle`** (Critical Unsafe Auto-Handles).
- **2 cases routed to `clarify`**: The system paused for clarification rather than immediate escalation. (e.g., Gold ID 3: `@AppleSupport [LINK]`). This is benign because `clarify` halts automated troubleshooting without making false factual assertions.

## 5. Unsafe Auto-Handle Patterns (12 Cases)

The 12 unsafe auto-handles are the highest risk error mode in an automated support agent.

### Distribution by Predicted Intent:

- **Battery / Charging**: 3 cases
- **Other / General**: 2 cases
- **Music / Media**: 2 cases
- **Settings / Features**: 1 cases
- **iOS / Software**: 1 cases
- **Connectivity**: 1 cases
- **Messages / Calling**: 1 cases
- **App Issue**: 1 cases

### Key Failure Mechanisms:
1. **Customer Frustration & Aggression Missed**:
   - E.g. Gold ID 6: *"Yes it’s successfully updated to iOS 11.0.2 - also do u really think that customer should DM u or u should try to reach out to customer??? 😡"*
   - The system classified the intent as `iOS / Software` with 0.97 confidence and top similarity 0.72. Because no hardware hazard or literal word 'human' was detected, it auto-handled despite high anger/sentiment escalation signals.
2. **Underlying Hardware / Persistent Bug Described Calmly**:
   - E.g. Gold ID 2: *"11.0.3 (15A432) Last night my keyboard disappeared while trying to text so I reset the phone settings. Still having problems."*
   - System classified as `Settings / Features` (0.93 conf) and auto-handled because similarity was 0.71. The user had already reset settings, but the phrase didn't match the troubleshooting regex exactly.
3. **DM / Private Account Follow-up Inquiries**:
   - Twitter interactions where users follow up on unread DMs or account suspensions were classified as `Other / General` with high retrieval scores against standard DM greeting templates.

## 6. Clarify Analysis (25 Cases)

The agent triggered `clarify` on 25 conversations (12.5% of dataset):

- **Human Escalation Alignment**: **23 NO**, **2 YES**.
- **Predicted Intent Distribution**: 24 `Other / General`, 1 `Messages / Calling`.
- **Human Intent Ground Truth**: 9 `iOS / Software`, 8 `Other / General`, 3 `Music / Media`, 1 `Settings / Features`, 1 `Connectivity`, 1 `Messages / Calling`, 1 `Battery / Charging`, 1 `iCloud / Backup / Data`.
- **Accuracy & Precision**: In 23 of 25 cases (92%), human annotators also agreed the case did not require escalation, confirming that clarifying ambiguous referents (e.g. *"It has"*, *"@AppleSupport DM Sent"*, *"I already have"*) is safe and avoids premature action.
- Asking for clarification prevented premature automated responses and prevented hallucination. Only 2 of the 25 clarify cases had human escalation marked as YES.

## 7. Five Representative Real Case Studies

### Case Study: False Positive Escalation (Low Retrieval Similarity) (Gold ID #9)
- **Customer Message**: `"@AppleSupport 7 and video/audio quality is choppy no matter what the connection is"`
- **Ground Truth**: Intent = `Music / Media`, Human Escalate = `NO`
- **Agent Prediction**: Action = `escalate`, Intent = `Music / Media` (Conf: `0.9657`), Top Sim: `0.6375`
- **Failure Diagnosis**: Intent was 96.6% confident, but top retrieval similarity (0.6375) was just below the 0.65 threshold. The agent safely escalated to a human specialist, whereas a human annotator deemed it standard troubleshooting.

### Case Study: False Positive Escalation (Classifier Uncertainty) (Gold ID #8)
- **Customer Message**: `"@AppleSupport iOS 11.0.2."`
- **Ground Truth**: Intent = `Battery / Charging`, Human Escalate = `NO`
- **Agent Prediction**: Action = `escalate`, Intent = `Battery / Charging` (Conf: `0.5178`), Top Sim: `0.9064`
- **Failure Diagnosis**: Retrieval similarity was very high (0.9064), but intent classifier confidence on the short snippet 'iOS 11.0.2.' was 0.5178 (< 0.60 gate). The safety policy escalated.

### Case Study: Unsafe Auto-Handle (Customer Frustration / Anger) (Gold ID #6)
- **Customer Message**: `"@AppleSupport Yes it’s successfully updated to iOS 11.0.2 - also do u really think that customer should DM u or u should try to reach out to customer??? 😡"`
- **Ground Truth**: Intent = `iOS / Software`, Human Escalate = `YES`
- **Agent Prediction**: Action = `auto_handle`, Intent = `iOS / Software` (Conf: `0.9724`), Top Sim: `0.7188`
- **Failure Diagnosis**: System detected confident technical intent and matched iOS update evidence, but missed the customer frustration / sarcasm / angry emoji, leading to an unsafe automated response.

### Case Study: Unsafe Auto-Handle (Missed Troubleshooting Recurrence) (Gold ID #2)
- **Customer Message**: `"@AppleSupport 11.0.3 (15A432) Last night my keyboard disappeared while trying to text so I reset the phone settings. Still having problems."`
- **Ground Truth**: Intent = `Messages / Calling`, Human Escalate = `YES`
- **Agent Prediction**: Action = `auto_handle`, Intent = `Settings / Features` (Conf: `0.9329`), Top Sim: `0.7099`
- **Failure Diagnosis**: Customer stated 'so I reset the phone settings. Still having problems.' The regex pattern missed this specific phrasing syntax ('reset the phone settings. Still having problems'), allowing an auto_handle when human marked escalation.

### Case Study: Benign Clarify on Vague Referent (Gold ID #1)
- **Customer Message**: `"@AppleSupport It has"`
- **Ground Truth**: Intent = `iOS / Software`, Human Escalate = `NO`
- **Agent Prediction**: Action = `clarify`, Intent = `Other / General` (Conf: `0.5048`), Top Sim: `0.7634`
- **Failure Diagnosis**: The input contains only 'It has' without an entity or context. The system correctly flagged ambiguity and asked for clarification, avoiding both blind guessing and unnecessary escalation.

## 8. Hypotheses Explaining Decision Failures

1. **Hypothesis 1: Static Hard Thresholds Cause Brittle Boundary Escalations**
   - Top similarity cutoff of `0.65` is a rigid hyperparameter. Queries with 0.63 - 0.64 cosine similarity against 22,738 cases often contain valid evidence, causing 50+ unnecessary escalations.
2. **Hypothesis 2: Lack of Sentiment / Frustration Gating in Escalation Policy**
   - The current policy only checks for explicit words like 'lawyer', 'human', or 'broken screen'. It lacks negative sentiment, profanity, or sarcasm detectors, which caused 5 of the 12 unsafe auto-handles.
3. **Hypothesis 3: Keyword-Based Troubleshooting Detection is Syntactically Narrow**
   - Customers describe failed prior attempts using varied syntax (e.g. *'reset settings, still having problems'* vs *'already tried resetting'*). Rigid regex misses subtle variations, causing unsafe auto-handles.
4. **Hypothesis 4: Multi-Turn Effective Query Dilution**
   - When customer messages are concatenated into an effective query, conversational pleasantries dilute the TF-IDF feature space and slightly depress embedding similarity.

## 9. Recommended Future Experiments (Post-Phase 8)

1. **Experiment 1: Adaptive Retrieval Thresholds by Intent**
   - Distinct intents have distinct semantic vector cluster densities. For high-density intents (`Battery / Charging`, `Connectivity`), a threshold of 0.65 works well; for broad intents (`iOS / Software`), a tuned threshold of 0.60 would reduce false positives by an estimated 35-40%.
2. **Experiment 2: Lightweight Sentiment / Anger Classifier Gate**
   - Add a fast rule or zero-shot sentiment check: if customer sentiment score < -0.6 or contains anger markers (e.g. 😡, multiple exclamation marks with caps), escalate immediately. This would eliminate ~40% of unsafe auto-handles.
3. **Experiment 3: Enhanced Troubleshooting Intent Extraction**
   - Upgrade regex pattern matching to a dependency-aware parser or small semantic classifier for detecting 'attempted troubleshooting failure'.
4. **Experiment 4: Calibrated Confidence Thresholding**
   - Use temperature scaling or isotonic regression to calibrate logistic regression probabilities, allowing safe relaxation of the 0.60 cutoff to 0.55 for top-performing classes.

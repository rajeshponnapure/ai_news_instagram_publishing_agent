# AI News Summary Report

Generated: 2026-05-27T17:45:13+00:00
Source: grdevelopers.co@gmail.com
Emails summarized: 1

## Executive Brief

- A Blog post by IBM Research on Hugging Face ITBench-AA: Frontier Models Score Below 50% on the First Benchmark for Agentic Enterprise IT Tasks - by Artificial Analysis and IBM ITBench-AA is built in partnership with.
- The harness (Stirrup) is held constant across all evaluated models, allowing an apples-to-apples comparison between models.
- Claude Opus 4.7 (Adaptive Reasoning, Max Effort) leads the leaderboard at 47% but is the most expensive at $5.38 per task.
- The headline score is the average across 59 tasks × 3 repeats.
- This is why some models with long trajectories underperform terser ones: Gemini 3.1 Pro Preview averages 83 turns and scores 30%, while Gemma 4 31B (Reasoning) averages 58 turns and scores 37%.
- DeepSeek V4 Pro (Reasoning, Max Effort) follows at 38%, with Gemma 4 31B (Reasoning) at 37%, ahead of Gemini 3.1 Pro Preview at 30%.

## Most Mentioned Companies

Google (1), Microsoft (1), Apple (1), Amazon (1), NVIDIA (1), Hugging Face (1), ElevenLabs (1), IBM (1)

## Most Mentioned Models

GPT-5.5 (1), Claude (1), Gemini 3.1 (1), Gemini 3.5 (1)

## Main Topics

model release (1), funding or business (1), regulation or safety (1), developer tools (1), hardware and compute (1), media generation (1)

## Voice Script Hooks

- Google just made a move in model release: ITBench-AA: Frontier Models Score Below 50% on the First Benchmark for Agentic Enterprise IT Tasks - by.

## Per-Email Summaries

### 1. ITBench-AA: Frontier Models Score Below 50% on the First Benchmark for Agentic Enterprise IT Tasks - by.

Source date: Wed, 27 May 2026 10:26:52 -0700
Confidence: 0.82
Article: https://huggingface.co/blog/ibm-research/itbench-aa
Article title: ITBench-AA: Frontier Models Score Below 50% on the First Benchmark for Agentic Enterprise IT Tasks — by Artificial Analysis and IBM

Article excerpt: A Blog post by IBM Research on Hugging Face

The harness (Stirrup) is held constant across all evaluated models, allowing an apples-to-apples comparison between models. A Blog post by IBM Research on Hugging Face ITBench-AA: Frontier Models Score Below 50% on the First Benchmark for Agentic Enterprise IT Tasks - by Artificial Analysis and IBM ITBench-AA is built in partnership with @IBMResearch based on their ITBench benchmark. In one public SRE task, the agent sees user-facing failures in the frontend path. More turns do not mean better answers. ITBench-AA is built in partnership with @IBMResearch based on their ITBench benchmark. Claude Opus 4.7 (Adaptive Reasoning, Max Effort) leads the leaderboard at 47% but is the most expensive at $5.38 per task. A Blog post by IBM Research on Hugging Face ITBench-AA: Frontier Models Score Below 50% on the First Benchmark for Agentic Enterprise IT Tasks - by Artificial Analysis and IBM ITBench-AA is built in partnership with. The harness (Stirrup) is held constant across all evaluated models, allowing an apples-to-apples comparison between models. Claude Opus 4.7 (Adaptive Reasoning, Max Effort) leads the leaderboard at 47% but is the most expensive at $5.38 per task. The headline score is the average across 59 tasks × 3 repeats. This is why some models with long trajectories underperform terser ones: Gemini 3.1 Pro Preview averages 83 turns and scores 30%, while Gemma 4 31B (Reasoning) averages 58 turns and scores 37%. DeepSeek V4 Pro (Reasoning, Max Effort) follows at 38%, with Gemma 4 31B (Reasoning) at 37%, ahead of Gemini 3.1 Pro Preview at 30%. Gemma 4 31B (Reasoning) scores 37% at $0.14 per task, outperforming Gemini 3.1 Pro Preview ($2.23 per task, 30%) on both score and cost. GLM-5.1 (Reasoning) leads open weights models at 40%, effectively tied with Gemini 3.5 Flash (high). For more information see: ITBench paper on arXiv: ITBench-AA leaderboard: ITBench-AA HuggingFace repo: The Open Agent Leaderboard Inside VAKRA: Reasoning, Tool Use, and Failure Modes of Agents All frontier models score below 50%, making ITBench-AA SRE one of the least saturated agentic benchmarks in our suite. The model must identify the minimal set of independent root-cause Kubernetes entities responsible for the incident. GLM-5.1 (Reasoning) scores 40% at $1.23 per task, matching Gemini 3.5 Flash (high) ($1.70) on score at lower cost. A Blog post by IBM Research on Hugging Face ITBench-AA: Frontier Models Score Below 50% on the First Benchmark for Agentic Enterprise IT Tasks - by Artificial Analysis and IBM ITBench-AA is built in partnership with @IBMResearch based on their ITBench benchmark. Claude Opus 4.7 (Adaptive Reasoning, Max Effort) leads at 47%, followed by GPT-5.5 (xhigh) at 46% and Qwen3.7 Max at 42%. All frontier models score below 50%, making ITBench-AA SRE one of the least saturated agentic benchmarks in our suite. For context, frontier models score considerably higher on Terminal-Bench. Turn counts vary nearly 3x and longer trajectories do not translate to higher accuracy. GPT-5.5 (xhigh) averages 31 turns per task at 46%, while Gemini 3.1 Pro Preview averages 83 turns at 30%. Models that over-investigate tend to surface upstream fault-injection mechanisms or co-occurring symptoms as false positives. GLM-5.1 (Reasoning) leads open weights models at 40%, effectively tied with Gemini 3.5 Flash (high). DeepSeek V4 Pro (Reasoning, Max Effort) follows at 38%, with Gemma 4 31B (Reasoning) at 37%, ahead of Gemini 3.1 Pro Preview at 30%. ITBench-AA SRE overview: 59 SRE tasks in total: 40 public tasks and 19 brand new, held-out tasks Each task provides a Kubernetes incident snapshot containing alerts, events, traces, metrics, logs, and application topology. The model must identify the minimal set of independent root-cause Kubernetes entities responsible for the incident. Faults span typical SRE failure modes including infrastructure, service, application, and chaos-injected incidents, such as resource quota exhaustion, rollout failures, connection pool exhaustion, and network partitions. Methodology details: Agentic harness: each task is solved by the model running in our open-source Stirrup reference harness, with shell access to a sandboxed file system containing the relevant logs and snapshots. 100-turn cap per task, 3 repeats per task. Models and agents submit a list of root-cause entities (Kubernetes Deployments, Services, Pods, etc.) they believe caused the incident. Each submission is compared against a ground-truth set of root causes provided by IBM Research. Scoring uses average precision at full recall: if a model misses any of the ground-truth root causes, it scores 0.0 for that repeat. If it identifies all of them, it is awarded a score equal to its precision - the share of its submitted entities that are actual root causes, i.e. true positives / (true positives + false positives). The headline score is the average across 59 tasks × 3 repeats. The harness (Stirrup) is held constant across all evaluated models, allowing an apples-to-apples comparison between models. Tasks require agents to investigate Kubernetes incident snapshots through shell commands and submit a structured JSON diagnosis identifying the responsible root-cause entities. In one public SRE task, the agent sees user-facing failures in the frontend path. It uses shell commands to inspect the offline snapshot: reviewing alerts shows the incident window, then traces/logs narrow the failure to frontend traffic. Topology pins down the affected services, and Kubernetes manifests reveal a network policy blocking the frontend. The successful diagnosis identifies the responsible root-cause entity: otel-demo/NetworkPolicy/frontend-block-all-ports. More turns do not mean better answers. Models that submit additional contributing entities beyond the true root cause get penalized: identifying the correct root cause but adding upstream mechanisms (e.g., a chaos-mesh controller) or co-occurring symptoms counts as a false positive under recall-gated precision. This is why some models with long trajectories underperform terser ones: Gemini 3.1 Pro Preview averages 83 turns and scores 30%, while Gemma 4 31B (Reasoning) averages 58 turns and scores 37%. Open weights models sit on the cost frontier of ITBench-AA SRE. Gemma 4 31B (Reasoning) scores 37% at $0.14 per task, outperforming Gemini 3.1 Pro Preview ($2.23 per task, 30%) on both score and cost. GLM-5.1 (Reasoning) scores 40% at $1.23 per task, matching Gemini 3.5 Flash (high) ($1.70) on score at lower cost. Claude Opus 4.7 (Adaptive Reasoning, Max Effort) leads the leaderboard at 47% but is the most expensive at $5.38 per task. ITBench-AA is built in partnership with @IBMResearch based on their ITBench benchmark. For more information see: ITBench paper on arXiv: ITBench-AA leaderboard: ITBench-AA HuggingFace repo: The Open Agent Leaderboard Inside VAKRA: Reasoning, Tool Use, and Failure Modes of Agents

Key points:
- A Blog post by IBM Research on Hugging Face ITBench-AA: Frontier Models Score Below 50% on the First Benchmark for Agentic Enterprise IT Tasks - by Artificial Analysis and IBM ITBench-AA is built in partnership with.
- The harness (Stirrup) is held constant across all evaluated models, allowing an apples-to-apples comparison between models.
- Claude Opus 4.7 (Adaptive Reasoning, Max Effort) leads the leaderboard at 47% but is the most expensive at $5.38 per task.
- The headline score is the average across 59 tasks × 3 repeats.
- This is why some models with long trajectories underperform terser ones: Gemini 3.1 Pro Preview averages 83 turns and scores 30%, while Gemma 4 31B (Reasoning) averages 58 turns and scores 37%.
- DeepSeek V4 Pro (Reasoning, Max Effort) follows at 38%, with Gemma 4 31B (Reasoning) at 37%, ahead of Gemini 3.1 Pro Preview at 30%.
Companies: Google, Microsoft, Apple, Amazon, NVIDIA, Hugging Face, ElevenLabs, IBM
Models: GPT-5.5, Claude, Gemini 3.1, Gemini 3.5
Topics: model release, funding or business, regulation or safety, developer tools, hardware and compute, media generation

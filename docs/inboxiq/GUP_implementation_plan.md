# AWS GPU Implementation Plan

## What AWS actually wants you to use (cheap paths)
- Preferred instances: G5 (A10G) or G6 (L4). This is where AWS expects most inference workloads to live.

| GPU  | Instance | Cost (approx.) | Why it matters              |
| ---- | -------- | -------------- | --------------------------- |
| A10G | G5       | ~$1.2–$1.6/hr  | Strong FP16, inexpensive    |
| L4   | G6       | ~$0.8–$1.2/hr  | Optimized specifically for inference |

*Roughly 10x cheaper than H100 and 4–5x cheaper than A100.*

## 1) GPU time-slicing (not MIG)
- Share a GPU across pods with soft isolation.
- Batch inference aggressively.
- This is how most real SaaS AI products run.
- Result: one ~$1/hr GPU can serve 10–50 concurrent customers.

## 2) Scale-to-zero (bigger savings than GPU choice)
- Idle GPUs are the real cost killer.
- Use a dedicated GPU node pool plus cluster autoscaler.
- Scale GPU nodes to zero when there is no traffic.
- Cold-start GPUs only when requests arrive.
- This saves more money than MIG in most cases.

## What big companies actually do
- Even with A100/H100 fleets, they do not run them 24/7.
- They do not MIG everything; MIG is a late-stage optimization.
- Large GPUs are used for peak throughput; smaller GPUs handle the rest.

## A sane architecture for your app
**Phase 1 — Right now**
- EKS with G5 or G6, GPU time-slicing, aggressive batching.
- Autoscale to zero; expect monthly GPU cost in the hundreds (not thousands).

**Phase 2 — When real load arrives**
- Add a second node pool.
- Mix cheap inference GPUs (L4/A10G) with occasional large GPU (A100) for heavier jobs.
- Route workloads by size.

**Phase 3 — Only if absolutely necessary**
- A100 with MIG for large models, long contexts, or high-value tenants.
- Never as the baseline.

## Hard truth
- GPU partitioning does not save money—utilization does.
- If GPUs are not already saturated: MIG will not help, H100 will hurt, and AWS bills will spike.

## Optional next steps
- Design a $300–$500/month GPU setup.
- Estimate cost per 1k inferences.
- Explore delaying GPUs entirely (CPU + quantized models).
- Compare AWS vs self-hosted vs hybrid approaches.

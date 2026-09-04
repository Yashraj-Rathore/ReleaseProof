# ReleaseProof Productization Blueprint

**Status:** Commercialization reference, not an implementation contract  
**Date:** September 2026  
**Goal:** Turn ReleaseProof from a strong engineering repository into a real developer SaaS with external users, repeat usage, and eventually paying teams.

## 1. Product Positioning

ReleaseProof should **not** compete with GitHub, Copilot, CodeRabbit, or Qodo as a generic AI code reviewer.

The product should sit **alongside GitHub + AI coding tools + existing CI** as a specialized verification layer.

### Core positioning

> **AI wrote it. AI reviewed it. ReleaseProof verifies it.**

Alternative:

> **Build with AI. Verify with evidence.**

### Core promise

ReleaseProof asks a narrower question than a normal reviewer:

> **What could this change break that the existing review and test suite have not actually proven?**

It should then gather evidence through change/blast-radius analysis, repository history, targeted verification, controlled execution, base-vs-candidate comparison, and a clear advisory result:

- **SHIP** — evidence supports the change.
- **REVIEW** — material concerns require human review.
- **HOLD** — verification found evidence of a regression or unsafe change.
- **UNKNOWN** — evidence is insufficient; never fake certainty.

## 2. Why This Is Different

The market already contains strong products:

- **GitHub Copilot Code Review:** AI-assisted PR review inside GitHub.
- **CodeRabbit:** AI PR review, repository context, automated checks, and advanced impact/blast-radius capabilities.
- **Qodo:** agentic code review, repository context, testing and code-quality workflows.
- **Traditional CI / static analysis:** known tests, linting, SAST, quality gates, and policy checks.

ReleaseProof is **not unique because it uses AI, understands PRs, generates tests, or examines blast radius**. Competitors already cover parts of those areas.

### Differentiation hypothesis

ReleaseProof should specialize in **systematic, reproducible, execution-grounded change verification**:

```text
PR opened or updated
        ↓
Immutable change snapshot
        ↓
Change intelligence + blast radius
        ↓
Historical/repository evidence
        ↓
Risk hypotheses
        ↓
Targeted verification plan
        ↓
Controlled execution
        ↓
Base vs candidate comparison
        ↓
Persisted evidence
        ↓
SHIP / REVIEW / HOLD / UNKNOWN
```

The commercial test is simple:

> **Does ReleaseProof repeatedly catch useful regressions or risky behavior that GitHub/Copilot + normal CI did not make obvious?**

If the answer is no, the product needs to pivot. More technical complexity alone is not validation.

## 3. Product Shape

Do **not** build a native iOS or Android app.

ReleaseProof should consist of three parts:

### A. GitHub App — primary daily experience

Users install ReleaseProof on selected repositories. The GitHub App should:

- receive installation and pull-request events;
- ingest a bounded PR snapshot;
- start verification automatically when a PR opens or updates;
- publish a GitHub Check/status;
- show the recommendation, major evidence, affected areas, and verification summary;
- link to the full evidence report.

Normal use should happen **inside GitHub**. Developers should not need to visit the ReleaseProof website for every PR.

Example GitHub result:

```text
ReleaseProof — HOLD

Risk: High
Affected components: 4
Targeted checks: 8
Behavioral differences: 1

Regression detected in partial-refund tax behavior.

View full evidence →
```

### B. ReleaseProof Verification Engine

This is the existing technical core:

- PR/change ingestion;
- blast-radius/change intelligence;
- repository/history retrieval;
- deterministic and ML risk evidence;
- targeted test proposals;
- controlled sandbox execution;
- base-vs-candidate differential verification;
- evidence fusion and advisory recommendation.

Do not expose the technology stack as the product value proposition. Customers buy **useful verification evidence**, not PyTorch, XGBoost, LangGraph, pgvector, or Celery.

### C. Web SaaS — setup and deep investigation

Suggested structure:

```text
releaseproof.com
├── Product / How it works
├── Demo
├── Security & privacy
├── Pricing
├── Documentation
└── Install on GitHub

app.releaseproof.com
├── Organizations
├── Repositories
├── Pull Requests
├── Verification Runs
├── Evidence Explorer
├── Usage
├── Team / Settings
└── Billing
```

The web application is for installation, configuration, historical reports, detailed evidence, organization controls, usage, and billing — **not the primary PR workflow**.

## 4. Ideal User Journey

```text
Developer hears about ReleaseProof
            ↓
       releaseproof.com
            ↓
        60–90 sec demo
            ↓
      Sign in with GitHub
            ↓
      Install GitHub App
            ↓
       Select repository
            ↓
          Open a PR
            ↓
 ReleaseProof runs automatically
            ↓
 Result appears inside GitHub
            ↓
     View evidence if needed
            ↓
 User enables more repositories
            ↓
          Paid plan
```

The product should minimize setup friction. The first useful result should arrive as soon as possible after installation.

## 5. First Commercial MVP

Do **not** wait for every ReleaseProof milestone to become customer-facing.

The public MVP should prove one workflow:

> **Automatically verify a GitHub PR and show whether ReleaseProof found evidence that the change may be unsafe.**

Minimum customer-facing scope:

1. GitHub App installation.
2. Select repository.
3. PR webhook ingestion.
4. Change/blast-radius analysis.
5. Targeted verification.
6. Controlled base-vs-candidate comparison where supported.
7. Simple SHIP / REVIEW / HOLD / UNKNOWN result.
8. GitHub Check with concise evidence.
9. Web evidence page.
10. Basic usage/security controls.

Avoid adding new impressive infrastructure unless it directly improves this user journey or the quality of verification.

## 6. Initial Target Customer

Start with **small AI-heavy engineering teams**, approximately 5–50 developers, that already use tools such as Copilot, Codex, Claude Code, Cursor, or other coding agents heavily.

Why this segment:

- they already believe in AI-assisted development;
- they create changes quickly;
- AI-generated code increases verification pressure;
- they can adopt a GitHub App faster than a large enterprise;
- a founder/CTO can make the purchasing decision without a long procurement cycle.

Do not initially optimize for banks or large regulated enterprises. Their security, procurement, self-hosting, compliance, and legal requirements can overwhelm an early product.

## 7. Validation Before Pricing Optimization

The first goal is **repeat use**, not revenue maximization.

Suggested validation sequence:

```text
1 external developer
        ↓
5–10 developers
        ↓
multiple real repositories
        ↓
repeat PR verification
        ↓
first team asking to enable more repos
        ↓
first paying team
```

Strong validation signals:

- a developer runs ReleaseProof on PR #2 without being asked;
- a team enables additional repositories;
- ReleaseProof finds a real issue that normal review/CI did not surface clearly;
- a developer changes a merge decision because of the evidence;
- a team asks for organization-wide installation;
- a team is willing to pay for continued use.

Weak validation signals:

- friends try it once;
- GitHub stars;
- landing-page visits;
- praise without repeat usage;
- sophisticated architecture with no external usage.

## 8. Competitive Proof Experiment

Before claiming strong differentiation, test ReleaseProof on a meaningful set of real PRs.

Compare:

**Baseline:** GitHub/Copilot + existing CI  
**Treatment:** GitHub/Copilot + existing CI + ReleaseProof

Track:

- meaningful regressions ReleaseProof uniquely surfaced;
- false positives;
- additional useful coverage;
- base-vs-candidate behavioral differences;
- developer merge-decision changes;
- analysis latency and cost;
- repeat usage;
- willingness to pay.

A compelling future sales proof is not:

> "ReleaseProof uses many AI/ML technologies."

It is:

> **"ReleaseProof caught this regression before merge, while the existing review and CI path did not."**

## 9. Monetization Hypothesis

Do not lock pricing until external usage exists.

Possible future structure:

### Free
- 1 repository
- limited monthly PR verifications
- core risk and verification result

### Team
- approximately **$49–$99/month** as an initial hypothesis
- multiple repositories
- higher verification limits
- historical evidence
- richer execution/differential verification
- team dashboard

### Business
- approximately **$199+/month** as an initial hypothesis
- more repositories/usage
- policy controls
- audit history
- advanced security
- private runners / stronger isolation options
- support

The important question is not whether the correct starting price is $49, $79, or $99. The first question is whether teams value the verification enough to use it repeatedly and pay anything.

## 10. What Not to Build Yet

Do not prioritize:

- native iOS/Android apps;
- another generic AI code-review chatbot;
- GitLab/Bitbucket before GitHub works well;
- VS Code extension before the GitHub workflow is validated;
- excessive new ML models;
- additional agents merely for technical sophistication;
- Kubernetes or distributed infrastructure unless required by real workload;
- enterprise compliance features before enterprise demand exists;
- perfect pricing;
- dozens of dashboard pages.

Potential later integrations after product-market evidence:

- CLI (`releaseproof verify`);
- Slack notifications;
- VS Code / IDE integration;
- GitLab / Bitbucket;
- private/self-hosted runners;
- enterprise identity and policy controls.

## 11. One-Month Productization Objective

A realistic first launch target is **not a mature company**. It is:

> **A deployed GitHub App + web dashboard that external developers can install and use on real PRs.**

Success after the first commercialization cycle would look like:

- public website and clear positioning;
- working GitHub App installation;
- automatic PR checks;
- useful evidence report;
- several external developers/repositories;
- repeat usage;
- measurable comparison against normal review + CI;
- at least one serious conversation about paying.

## 12. Final Product Principle

ReleaseProof should not try to beat GitHub at being GitHub or Copilot at being Copilot.

It should become the **independent verification layer** that fits into the existing workflow:

```text
AI / developer writes code
          ↓
GitHub + reviewer reviews it
          ↓
Existing CI runs expected checks
          ↓
ReleaseProof investigates what may still be wrong
          ↓
Execution-grounded evidence
          ↓
Human makes the final decision
```

**North-star question:**

> **Did ReleaseProof produce evidence that materially improved the team's confidence or prevented a bad change from shipping?**

If yes repeatedly, there is a product. If not, change the product rather than simply adding more technology.

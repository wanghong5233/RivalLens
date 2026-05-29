---
name: evidence-must-cite-source
description: Require every key claim to include at least one evidence id citation.
version: 1.0.0
tags:
  - qa
  - citation
  - baseline
applies_to: qa_rule
dependencies: []
---

## Rule DSL

```yaml
id: evidence_must_cite_source
when:
  section_title_contains: ["Feature", "Pricing", "User Feedback"]
require:
  section_has_evidence_refs: true
severity: warning
reject_to: writer
message: "Each core section must reference at least one evidence id."
```

## Why

This rule prevents fluent-but-unsupported summaries from passing QA.

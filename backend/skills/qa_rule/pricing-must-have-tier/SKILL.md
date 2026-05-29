---
name: pricing-must-have-tier
description: Ensure pricing sections include at least one concrete tier or plan detail.
version: 1.0.0
tags:
  - qa
  - pricing
  - baseline
applies_to: qa_rule
dependencies: []
---

## Rule DSL

```yaml
id: pricing_must_have_tier
when:
  section_title_contains: ["Pricing"]
require:
  section_content_min_chars: 80
severity: warning
reject_to: writer
message: "Pricing section should include concrete tier details or plan-level evidence."
```

## Why

Pricing comparisons are low value when only qualitative statements are present.

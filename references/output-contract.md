# Output contract

## Mapper output

`review_mapper` writes `.review/semantic-slices.json`:

```json
{
  "summary": "short change summary",
  "risk_areas": ["security", "api_contract"],
  "slices": [
    {
      "id": "post-invoices-endpoint",
      "title": "POST /invoices endpoint",
      "intent": "Create invoices through the new route",
      "entrypoints": ["POST /api/invoices", "createInvoiceHandler"],
      "files": ["src/api/invoices.ts", "src/services/invoices.ts", "src/api/invoices.test.ts"],
      "changed_symbols": ["createInvoiceHandler", "CreateInvoiceRequest"],
      "context_files": ["src/auth/session.ts", "src/db/invoices.ts"],
      "risk_tags": ["api_contract", "security", "test"],
      "required_reviewers": ["review_slice_context", "review_contract_api", "review_security", "review_tests"],
      "suggested_tests": ["pnpm test src/api/invoices.test.ts"],
      "related_slices": ["invoice-shared-service"],
      "reason": "Route/auth/schema/service/test path is one independently reviewable behavior."
    }
  ],
  "deterministic_checks": [
    {"command": "pnpm test src/api/invoices.test.ts", "reason": "new route tests", "cheap": true, "required": false}
  ]
}
```

## Reviewer output

Reviewers return:

```json
{
  "agent": "review_diff_bug",
  "loop": 1,
  "scope": "whole_diff|slice:<id>|specialist:<name>",
  "summary": "short summary",
  "findings": []
}
```

Each finding:

```json
{
  "id": "agent-local-stable-id",
  "title": "short title",
  "severity": "blocking|important|nit|question|pre_existing",
  "category": "correctness|security|data_integrity|migration|api_contract|concurrency|performance|test|maintainability|dx",
  "file": "repo-relative path",
  "line_start": 1,
  "line_end": 1,
  "introduced_by_change": true,
  "confidence": 0.0,
  "claim": "specific issue",
  "evidence": "files/symbols/code path",
  "suggested_fix": "minimal direction",
  "verification_needed": "how to confirm"
}
```

## Verifier output

```json
{
  "verifications": [
    {
      "candidate_id": "canonical or raw id",
      "verdict": "confirmed|rejected|uncertain|downgraded",
      "confidence": 0.0,
      "reason": "why",
      "evidence": "specific code/test evidence",
      "minimal_reproduction_or_test": "command, test, or reasoning path",
      "recommended_severity": "blocking|important|nit|question|pre_existing"
    }
  ]
}
```

## Final report verdicts

- `ready`: no confirmed blocking/important findings remain.
- `needs_fixes`: confirmed blocking/important findings remain and can be fixed from code context.
- `needs_manual_decision`: only human judgment items remain.
- `blocked`: validation or review cannot proceed safely.

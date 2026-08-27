# ADR-009 — No Shared Training on Private Customer Code by Default
**Status:** Accepted

Private customer source, prompts, retrieved text, generated patches, and outcomes are not pooled into a global training corpus by default. Any future cross-tenant learning requires an explicit product/privacy design, legal review, tenant opt-in, deletion semantics, and provenance. Tenant data is not silently reused for model improvement.

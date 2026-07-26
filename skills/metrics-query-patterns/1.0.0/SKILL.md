# Metrics Query Patterns

Use these patterns to efficiently query metrics:
- Always specify `maxSamples=1` for latest data.
- Query stat keys first before requesting metric values to avoid large unconstrained queries.

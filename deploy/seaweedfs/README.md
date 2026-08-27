# SeaweedFS local configuration

The active `s3.local.json` contains local credentials and is ignored by Git. Generate it from the
selected environment file with:

```text
uv run --env-file .env python -m eng.configure_local
```

The command writes only the bounded S3 identity/actions required by ADR-016. Never place production
credentials in this directory.

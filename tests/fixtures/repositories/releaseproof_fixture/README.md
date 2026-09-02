# ReleaseProof fixture repository

This is a deliberately tiny, fictional and synthetic Python repository authored for deterministic
ReleaseProof tests. It contains no mined GitHub data, customer code, credentials, network access,
or production outcomes. It is licensed under MIT; see `LICENSE`.

ReleaseProof treats these files as inert source fixtures on application, Celery, and developer
hosts. M9 may execute only an exact hashed copy in the dedicated sandbox boundary. M3 uses the
Python files to prove static imports, reverse reachability, impacted-test mapping and explicit
dynamic/unsupported-language findings.

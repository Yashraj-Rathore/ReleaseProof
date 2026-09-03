# Datasets
Do not commit private customer source, secrets, large raw corpora, model weights, or unlicensed data. Commit only small licensed/synthetic fixtures, manifests, schemas, checksums, and reproducible acquisition/extraction instructions permitted by the source license.

`public/m11_semantic_dataset_v1.json` is a small generated semantic derivative of the admitted M4
fictional fixture. It preserves the exact M4 source/admission/split lineage, includes only bounded
pre-outcome path/status/patch text, and carries separately licensed outcome-blind synthetic category
annotations. Rebuild/check it with `python -m eng.evaluate_m11_semantic --check`; do not hand-edit it.

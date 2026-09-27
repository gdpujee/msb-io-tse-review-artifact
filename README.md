# MSB-IO / TSE reviewer artifact

This repository is the versioned empirical artifact for “When the Answer Is in the Query: Temporal Query Provenance and Evaluation Validity in Multilingual Repository-Level Localization.” The main and supplementary PDFs are submitted separately to IEEE TSE.

## Contents

- benchmark/msb_io/: 1,791 issue-only queries, SHA-256 hashes, labels, and field availability.
- results/raw_v2/: 14,328 issue-only lexical/structural rows and 1,791 dense rows.
- results/contrast_leaky_v1/ and results/contrast_leaky_dense_v1/: superseded-query contrast rows with distinct protocol identifiers.
- results/tables_v2/, results/audit_v2/, results/figures/: generated tables, audits, and six figures.
- experiments/ and tests/: analysis, verification, query construction, evaluation, and figure scripts.
- paper/manuscript_ESE_v2.md: manuscript source needed for the number auditor.
- SHA256SUMS: manifest for every other file in this curated repository.
- reproduction_package.zip and ARTIFACT_MANIFEST.sha256: deterministic archive of the same reviewer-safe scientific files, built by experiments/build_artifact.py --verify.

## Check the supplied evidence

Use Python 3.13 with the pinned dependencies. From the repository root:

    python -m pip install -r requirements-lock.txt
    shasum -a 256 -c SHA256SUMS
    python experiments/verify_supplied_snapshot.py
    python experiments/audit_manuscript_v2.py
    python experiments/verify_contrast_v2.py

The standalone snapshot verifier checks all four supplied result families, query hashes, and the manifest without downloads. The original independent 14,328-row verifier and dense verifier also check against upstream instance metadata. First run python experiments/fetch_data.py, then python experiments/verify_results_v2.py and python experiments/verify_dense_v2.py. Full evaluation reruns additionally reconstruct local repository indexes at the pinned base commits. Downloaded upstream JSONL files, repository source/indexes, and model weights are deliberately not redistributed. The dense rerun downloads the pinned SweRankEmbed-Small weights separately.

## Data provenance and privacy

Only scientific evidence and its verification code are included. This repository excludes private workstation paths, credentials, downloaded repository source/indexes, model weights, cover letters, and internal research/review notes. Host-specific output locations in ten contrast completion markers were changed to relative paths; raw predictions, query hashes, metrics, and protocol identifiers are unchanged.

The exact query strings in benchmark/msb_io/msb_io.jsonl derive from **public upstream issues**. Some upstream issue text contains contributor email addresses or example home-directory paths. Those strings remain verbatim because redaction would invalidate the published query hashes and experiment. They are not author workstation paths or credentials. A scan of this repository found no private key blocks, high-confidence API/GitHub tokens, or author-specific home-directory paths. See ARTIFACT_LICENSES.md: the MIT license covers our code, not third-party benchmark text or repository content.

Use the Git commit hash to identify this reviewer snapshot. The submitted paper and separate six-page figure/table supplement should be read alongside this artifact.

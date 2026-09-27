# Artifact licensing and redistribution boundaries

The experiment implementation, evaluation scripts, manuscript source, and
generated summary tables are authored project material released under the
MIT License (see `LICENSE` in the repository root).

The following third-party materials are not relicensed by this artifact:

- **Multi-SWE-bench rows.** The upstream dataset card is tagged
  `license:other`; its prose describes CC0 subject to ByteDance intellectual-
  property rights and also requires compliance with the licenses of the
  underlying repositories.
- **Repository source.** Each GitHub project retains its own license. Repository
  content is streamed from the recorded base commit to construct local indexes
  and must not be redistributed under a single blanket license.
- **MTEB MultiSWEbenchRR.** Public query rows are fetched from the upstream
  dataset. The checked-in audit stores query identifiers, classifications, and
  exact-match provenance, not the query text or corpus.
- **SweRankEmbed-Small.** Model weights remain governed by the upstream
  CC-BY-NC-4.0 license. They are downloaded from the exact recorded revision and
  are not bundled.

Before making an anonymous review archive, include source and generated results,
but exclude `data/raw/`, `data/index/`, `.hf_cache/`, downloaded model weights,
and all repository source snapshots.

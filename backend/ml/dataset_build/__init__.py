"""Six-stage rebuild of backend/data into a clean data/dataset/ release.

  1 index       ml.dataset_build.index        scan sources, md5 + dhash
  2 dedup       ml.dataset_build.dedup        exact + near duplicates, BEFORE any split
  3 rebalance   ml.dataset_build.rebalance    pick ~50k detector images, rare classes whole
  4 restructure ml.dataset_build.restructure  class plan: aggregates, prune, fold, cap
  5 split       ml.dataset_build.split        group-aware leak-free train/val
  6 emit        ml.dataset_build.emit         copy files, write configs, verify

Driven by scripts/build_dataset.py, which owns stage markers and resume.
Every module here is pure and independently testable; none of them touch the
source trees destructively.
"""

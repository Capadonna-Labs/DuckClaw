# Training Datasets

Dataset policy for `packages/agents/train`:

- `raw/`: source traces or exports; do not version real user data.
- `curated/`: regenerated JSONL after filters/sanitization.
- `golden/`: small, sanitized fixtures that may be versioned and tested.

Large, private, or regenerated files belong outside Git unless a spec explicitly marks them as sanitized fixtures.

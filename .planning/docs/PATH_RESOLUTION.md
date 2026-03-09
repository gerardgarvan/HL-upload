# Path Resolution

**Reference:** `src/load/config.py`, `config/paths.toml`

## HPC Layout

| Path | Resolution | Notes |
|------|------------|-------|
| `data_root` | `/orange/erin.mobley-hl.bcu/Mailhot_V1_20250915` | Read-only source CSVs |
| `scratch_root` | `/blue/erin.mobley-hl.bcu` | Scratch and derived outputs |
| `parquet_dir` | `scratch_root / output.parquet_dir` | Parquet files |
| `datastructure_path` | `project_root / datastructure.txt` | Resolved relative to project root |
| `valuesets_path` | `project_root / valuesets.csv` | Resolved relative to project root |

## parquet_dir Resolution

```python
parquet_dir = scratch_root / parquet_rel
```

Where `parquet_rel` comes from `[paths.output].parquet_dir` in `paths.toml`.

- **Current config:** `parquet_dir = "hpc-upload/parquet"`  
  → Resolved: `/blue/erin.mobley-hl.bcu/hpc-upload/parquet`
- **Alternative (ROADMAP):** `parquet_dir = "hl-clean/parquet"`  
  → Resolved: `/blue/erin.mobley-hl.bcu/hl-clean/parquet`
- **Default (if output.parquet_dir absent):** `hl-clean/parquet`

## Derived Paths

Scripts derive additional paths from `parquet_dir`:

- `parquet_clean_dir = parquet_dir.parent / "parquet_clean"`
- `derived_dir = parquet_dir.parent / "derived"`
- `logs_dir` from `output.logs_dir` (relative to scratch_root if not absolute)

## Local Development

For local dev or staged subsets, edit `config/paths.toml`:

- Set `scratch_root` to a local path (e.g. project root or temp dir)
- Ensure `parquet_dir` points to where Parquet files live
- `data_root` and `datastructure_path` must be valid for convert/validate

## See Also

- [HPC_UPLOAD_SYNC.md](HPC_UPLOAD_SYNC.md) — sync strategy for hpc-upload
- [CONCERNS.md](../codebase/CONCERNS.md) § Data Paths

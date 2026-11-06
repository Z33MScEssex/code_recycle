# Benchmarks

## CodeSearchNet (public)

Download the Python test split (28.7 MB) from the Hugging Face copy of CodeSearchNet. The original
S3 links in the CodeSearchNet README no longer work.

```bash
curl -L -o data/csn_python_test.parquet \
  https://huggingface.co/datasets/code-search-net/code_search_net/resolve/main/python/test-00000-of-00001.parquet
pip install pyarrow
python bench/codesearchnet.py
```

Each function keeps its own repository's licence, so the data is never committed here.

## Own research entries

`python bench/own_entries.py path/to/code_recycle.toml --detail somewhere_private.txt`

Uses your own index. The per-case detail names your files, so keep it out of public repos.

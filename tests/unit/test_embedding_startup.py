"""Backend startup must not depend on loading the embedding model runtime."""

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np


def test_application_routes_load_without_importing_embedding_runtime():
    root = Path(__file__).resolve().parents[2]
    code = """
import sys

class BlockEmbeddingRuntime:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'sentence_transformers' or fullname.startswith('sentence_transformers.'):
            raise RuntimeError('embedding runtime imported during application startup')

sys.meta_path.insert(0, BlockEmbeddingRuntime())
from app.main import app
paths = set(app.openapi()['paths'])
assert {'/api/rag/search', '/api/analysis/upload', '/health'} <= paths
print('startup routes ready without embedding runtime')
"""
    env = os.environ.copy()
    env.update(
        DATABASE_HOST="127.0.0.1",
        DATABASE_PORT="5432",
        DATABASE_NAME="startup_test_only",
        DATABASE_USER="test_only",
        DATABASE_PASSWORD="test_only",
        MODEL_PROVIDER="fake",
        DASHSCOPE_API_KEY="",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        PYTHONUTF8="1",
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=45,
    )
    assert result.returncode == 0, result.stderr
    assert "startup routes ready" in result.stdout


def test_embedding_model_is_loaded_when_service_is_used(monkeypatch):
    from app.rag.embeddings import EmbeddingService

    calls = []

    class Model:
        def __init__(self, model_name):
            calls.append(("load", model_name))

        def encode(self, texts, *, show_progress_bar):
            calls.append(("encode", texts, show_progress_bar))
            return np.array([[float(len(text)), 0.5] for text in texts])

    monkeypatch.setitem(
        sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=Model)
    )
    service = EmbeddingService("local-fixture")
    assert service.embed_query("hello") == [5.0, 0.5]
    assert service.embed_documents(["a", "bb"]) == [[1.0, 0.5], [2.0, 0.5]]
    assert calls == [
        ("load", "local-fixture"),
        ("encode", ["hello"], False),
        ("encode", ["a", "bb"], False),
    ]

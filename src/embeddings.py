"""
Portable embedding helper with optional OpenAI support and a deterministic fallback.
"""
from __future__ import annotations

import hashlib
import os
from typing import List, Optional

DEFAULT_DIM = 1536


def _hash_embedding(text: str, dim: int = DEFAULT_DIM) -> List[float]:
  # Deterministic cheap fallback so the pipeline can run without an API key.
  h = hashlib.sha256(text.encode("utf-8")).digest()
  vals = []
  for i in range(dim):
    vals.append(((h[i % len(h)] / 255.0) - 0.5) * 2.0)
  return vals


def embed_text(text: str, model: Optional[str] = None) -> List[float]:
  """
  Return an embedding for text. Uses OpenAI if configured; otherwise a deterministic hash fallback.
  """
  text = text or ""
  model_name = model or os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
  api_key = os.getenv("OPENAI_API_KEY")
  if api_key:
    try:
      import openai

      client = openai.OpenAI(api_key=api_key)
      resp = client.embeddings.create(model=model_name, input=text)
      return resp.data[0].embedding
    except Exception:
      # Fall back if OpenAI call fails for any reason.
      pass
  return _hash_embedding(text, DEFAULT_DIM)

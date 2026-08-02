"""Cross-encoder rerank ONNX minimal (ms-marco-MiniLM-L-6-v2 qint8, ~25MB).

Model: temsa/ms-marco-MiniLM-L-6-v2-onnx-cpu-qint8 via HF (cache lokal).
Ponytail: tanpa torch/transformers — tokenizers.BertWordPieceTokenizer + onnxruntime.
Jika model gagal download/load -> rerank nonaktif (caller fallback).
"""
import os
import urllib.request

from tokenizers import BertWordPieceTokenizer

MODEL_ID = "temsa/ms-marco-MiniLM-L-6-v2-onnx-cpu-qint8"
FILES = ("onnx/model.onnx", "vocab.txt", "config.json")
MAX_LEN = 512
_CACHE_DIR = os.environ.get("MEMO_CACHE_DIR") or os.path.expanduser("~/.cache/memo/reranker")


def _path(name: str) -> str:
    return os.path.join(_CACHE_DIR, name.replace("/", "_"))


def _ensure_model() -> str:
    onnx_path = _path("onnx/model.onnx")
    if os.path.exists(onnx_path):
        return onnx_path
    os.makedirs(_CACHE_DIR, exist_ok=True)
    for name in FILES:
        dest = _path(name)
        if os.path.exists(dest):
            continue
        url = f"https://huggingface.co/{MODEL_ID}/resolve/main/{name}"
        urllib.request.urlretrieve(url, dest + ".tmp")
        os.rename(dest + ".tmp", dest)
    return onnx_path


class CrossReranker:
    """Rerank (query, doc) pairs -> skor relevansi (logit positif)."""

    def __init__(self, threads: int = 2):
        import numpy as np  # lazy: numpy import ~1s, server start harus cepat
        import onnxruntime  # lazy: import ORT ~1-2s
        self._np = np
        so = onnxruntime.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        self.session = onnxruntime.InferenceSession(
            _ensure_model(), so, providers=["CPUExecutionProvider"])
        self.tok = BertWordPieceTokenizer(_path("vocab.txt"))
        self.tok.enable_truncation(max_length=MAX_LEN)

    def rerank(self, pairs: list[tuple[str, str]]) -> list[float]:
        ids, mask, seg = [], [], []
        for q, d in pairs:
            enc = self.tok.encode(q, d)
            n = len(enc.ids)
            ids.append(enc.ids + [0] * (MAX_LEN - n))
            mask.append([1] * n + [0] * (MAX_LEN - n))
            seg.append(enc.type_ids + [0] * (MAX_LEN - n))
        out = self.session.run(
            None,
            {"input_ids": self._np.array(ids, dtype=self._np.int64),
             "attention_mask": self._np.array(mask, dtype=self._np.int64),
             "token_type_ids": self._np.array(seg, dtype=self._np.int64)},
        )[0]  # (N,1): single relevance logit
        return [float(logits[0]) for logits in out]

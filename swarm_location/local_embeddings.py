"""Pinned CPU semantic embeddings over native Shinka's local OpenAI interface.

Only model-asset preparation downloads files. Inference uses ONNX Runtime locally,
without torch, provider credentials, executable model code, or cloud fallback.
"""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import threading
import urllib.request

from .persistence import exclusive, file_digest

MODEL = 'swarm-minilm-l6-v2'
REVISION = '1110a243fdf4706b3f48f1d95db1a4f5529b4d41'
REPOSITORY = 'sentence-transformers/all-MiniLM-L6-v2'
ASSETS = {
    'onnx/model.onnx': ('sha256', '6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452'),
    'tokenizer.json': ('git_blob_sha1', 'cb202bfe2e3c98645018a6d12f182a434c9d3e02'),
}


def asset_hash(path, kind):
    if kind == 'sha256':
        return file_digest(path)
    data = Path(path).read_bytes()
    return hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()


def prepare(directory, download=False):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with exclusive(directory/'.prepare.lock'):
        for name, (kind, expected) in ASSETS.items():
            target = directory/name
            if not target.exists():
                if not download:
                    raise RuntimeError('local embedding assets missing; run scripts/prepare_local_embeddings.py --download')
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_suffix('.part')
                url = f'https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{name}'
                # Public weights, not inference; no Authorization header supplied.
                try:
                    with urllib.request.urlopen(url, timeout=120) as response, temporary.open('wb') as stream:
                        while block := response.read(1024*1024):
                            stream.write(block)
                    if asset_hash(temporary, kind) != expected:
                        raise ValueError('downloaded embedding asset checksum mismatch')
                    temporary.replace(target)
                finally:
                    temporary.unlink(missing_ok=True)
            if asset_hash(target, kind) != expected:
                raise ValueError(f'embedding asset differs from pinned model: {name}')
    return {'model': MODEL, 'repository': REPOSITORY, 'revision': REVISION,
            'files': {name: file_digest(directory/name) for name in ASSETS},
            'pooling': 'attention-mask mean; all 254-token chunks; token-weighted mean; L2 normalize',
            'dimensions': 384, 'inference': 'onnxruntime CPU single thread'}


class Encoder:
    def __init__(self, directory):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.tokenizer = Tokenizer.from_file(str(Path(directory)/'tokenizer.json'))
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(Path(directory)/'onnx/model.onnx'),
                                            sess_options=options, providers=['CPUExecutionProvider'])
        self.names = {item.name for item in self.session.get_inputs()}
        self.cls = self.tokenizer.token_to_id('[CLS]')
        self.sep = self.tokenizer.token_to_id('[SEP]')
        if self.cls is None or self.sep is None:
            raise ValueError('pinned model tokenizer is missing special tokens')

    def encode(self, texts):
        import numpy as np
        vectors, token_count = [], 0
        for text in texts:
            ids = self.tokenizer.encode(text, add_special_tokens=False).ids
            token_count += len(ids)
            chunks = [ids[i:i+254] for i in range(0, len(ids), 254)] or [[]]
            total = np.zeros(384, dtype=np.float64)
            weight_sum = 0
            for chunk in chunks:
                data = np.array([[self.cls, *chunk, self.sep]], dtype=np.int64)
                feed = {'input_ids': data, 'attention_mask': np.ones_like(data),
                        'token_type_ids': np.zeros_like(data)}
                # Each chunk has no padding; ordinary attention-mask mean pooling.
                hidden = self.session.run(None, {k:v for k,v in feed.items() if k in self.names})[0]
                vector = hidden[0].mean(axis=0)
                weight = max(1, len(chunk))
                total += vector * weight
                weight_sum += weight
            total /= weight_sum
            norm = np.linalg.norm(total)
            if not np.isfinite(total).all() or not norm > 0:
                raise ValueError('local embedding inference returned invalid vector')
            vectors.append((total/norm).tolist())
        return vectors, token_count


@contextmanager
def server(directory, port, failure_dir=None):
    identity = prepare(directory)
    encoder = Encoder(directory)
    from importlib import metadata
    identity['runtime_versions'] = {name: metadata.version(name) for name in ('onnxruntime', 'tokenizers', 'numpy')}
    def failed():
        if failure_dir:
            from .subscription import block
            block(failure_dir, 'Local semantic embedding inference failed; no remote fallback')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Do not put source text or request headers in logs.
        def do_POST(self):
            if self.path != '/v1/embeddings':
                self.send_error(404)
                return
            try:
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= 8_000_000:
                    raise ValueError('invalid embedding request size')
                request = json.loads(self.rfile.read(size))
                if request.get('model') != MODEL or request.get('encoding_format', 'float') != 'float':
                    raise ValueError('unknown local embedding model or format')
                texts = request.get('input')
                texts = [texts] if isinstance(texts, str) else texts
                if not isinstance(texts, list) or not texts or not all(isinstance(t, str) for t in texts):
                    raise ValueError('embedding input must be text or a nonempty text list')
                vectors, tokens = encoder.encode(texts)
                response = {'object': 'list', 'model': MODEL,
                    'data': [{'object': 'embedding', 'index': i, 'embedding': v} for i,v in enumerate(vectors)],
                    'usage': {'prompt_tokens': tokens, 'total_tokens': tokens}}
                encoded = json.dumps(response, allow_nan=False).encode()
            except Exception:
                failed()
                self.send_error(500, 'local embedding failure; remote fallback disabled')
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
    # Bind only IPv4 loopback; never attach to an unknown pre-existing service.
    http = HTTPServer(('127.0.0.1', port), Handler)
    http.timeout = 1
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield identity
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=5)

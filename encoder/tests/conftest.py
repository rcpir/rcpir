import base64
import json
from pathlib import Path

import numpy as np
import pytest

SEED = bytes(range(16))


def write_jsonl(path: Path, payloads, extra=None) -> Path:
    with open(path, "w") as f:
        for k, d in enumerate(payloads):
            obj = {"data": base64.b64encode(d).decode()}
            if extra:
                obj.update(extra(k))
            f.write(json.dumps(obj) + "\n")
    return path


def random_payloads(rng: np.random.Generator, t: int, max_len: int) -> list[bytes]:
    return [rng.integers(0, 256, size=int(rng.integers(0, max_len + 1)), dtype=np.uint8).tobytes()
            for _ in range(t)]


@pytest.fixture
def rng():
    return np.random.default_rng(12345)

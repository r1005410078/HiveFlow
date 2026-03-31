from importlib import import_module
from pathlib import Path
import os
import sys

import uvicorn


def _ensure_src_on_path() -> None:
    src_dir = Path(__file__).resolve().parents[1] / "src"
    src_str = str(src_dir)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)


_ensure_src_on_path()
create_app = import_module("interfaces.http.app").create_app


if __name__ == "__main__":
    host = os.getenv("HF_HOST", "0.0.0.0")
    port = int(os.getenv("HF_PORT", "8000"))
    uvicorn.run("interfaces.http.app:create_app", host=host, port=port, factory=True)

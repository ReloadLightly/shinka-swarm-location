"""Local seed evaluation worker. Process separation is NOT a security sandbox."""
import contextlib
import importlib.util
import json
import sys
from pathlib import Path


def main() -> None:
    path = Path(sys.argv[1]).resolve()
    kwargs = json.load(sys.stdin)
    spec = importlib.util.spec_from_file_location("candidate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with contextlib.redirect_stdout(sys.stderr):
        spec.loader.exec_module(module)
        result = module.run_experiment(**kwargs)
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()

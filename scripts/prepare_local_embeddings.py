"""Download and verify public local-embedding weights; makes no LLM/API call."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from swarm_location.local_embeddings import prepare
if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory', type=Path, default=ROOT/'data/local_embeddings')
    p.add_argument('--download', action='store_true')
    args = p.parse_args()
    print(json.dumps(prepare(args.directory, args.download), indent=2))

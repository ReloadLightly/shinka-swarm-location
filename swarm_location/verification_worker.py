"""Trusted verifier entry point. Limits apply before reading untrusted journals."""
import os
from pathlib import Path
import resource
import sys


def main():
    request_path, response_path, memory, cpu, output_bytes = sys.argv[1:]
    resource.setrlimit(resource.RLIMIT_AS, (int(memory)*1024*1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (int(cpu),) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (int(output_bytes),) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import json
    from swarm_location.core import Instance, ShortestPathCoverage
    from swarm_location.prepared import load_prepared
    from swarm_location.anytime import postprocess
    from swarm_location.persistence import atomic_json
    request = json.loads(Path(request_path).read_text())
    if request.get('prepared_path'):
        oracle = load_prepared(request['prepared_path'], request['prepared_sha256'])
        instance = oracle.instance
    else:
        instance = Instance.from_dict(request['instance'])
        oracle = ShortestPathCoverage(instance)
    result = postprocess(instance, request['k'], request['checkpoints'], request['capture'],
                         request['baseline'], request['bounds'], oracle)
    atomic_json(response_path, result)


if __name__ == '__main__':
    main()

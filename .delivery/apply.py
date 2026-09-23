"""Temporary reviewed-patch delivery; removed from the final source tree."""
from pathlib import Path
import base64
import bz2
import hashlib
import json
import os
import shutil
import subprocess
import sys

REPO = 'ReloadLightly/shinka-swarm-location'
BRANCH = 'work/staged-comparators'
assert os.environ['GITHUB_REPOSITORY'] == REPO
assert os.environ['GITHUB_REF_NAME'] == BRANCH

def run(*args, log=None):
    print('+ ' + ' '.join(args), flush=True)
    if log:
        with Path(log).open('w') as stream:
            result = subprocess.run(args, stdout=stream, stderr=subprocess.STDOUT)
        print(Path(log).read_text()[-24000:], flush=True)
        result.check_returncode()
    else:
        subprocess.run(args, check=True)

def out(*args):
    return subprocess.check_output(args, text=True).strip()

payload = ''.join(Path(f'.delivery/part{i}.b64').read_text() for i in range(4))
patch = bz2.decompress(base64.b64decode(payload, validate=True))
assert hashlib.sha256(patch).hexdigest() == 'bad98fc3c7b5395ab7b2b93b13a49755f1e33fb5162c85605c2c023fd534a02f'
patch_path = Path('/tmp/staged-comparators.patch')
patch_path.write_bytes(patch)
run('git', 'apply', '--check', str(patch_path))
run('git', 'apply', str(patch_path))
shutil.rmtree('.delivery')
run('git', 'diff', '--check')
run('git', 'config', 'user.name', 'github-actions[bot]')
run('git', 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')
run('git', 'add', '-A')
run('git', 'commit', '-m', 'Integrate versioned M4 screening and assessment comparators')
source_commit = out('git', 'rev-parse', 'HEAD')
evidence = Path('results/step4/integration')
evidence.mkdir(parents=True, exist_ok=False)
run(sys.executable, '-m', 'pip', 'install', '-r', 'requirements-certificates.txt')
run(sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v', log=evidence/'tests.txt')
run(sys.executable, 'scripts/check_m4_continuity.py', '--output', str(evidence/'continuity.json'))
run(sys.executable, 'scripts/prepare_research.py', '--split', 'development', '--download', '--comparison-profile', 'configs/comparisons_m4.json', '--output', 'data/commissioning_m4', log=evidence/'prepare.txt')
run(sys.executable, '-m', 'pip', 'install', '-e', '.', '-r', 'requirements-shinka.txt')
run('docker', 'pull', 'python:3.11-slim')
image = out('docker', 'image', 'inspect', 'python:3.11-slim', '--format', '{{.Id}}')
common = ['--config', 'configs/evolution_m3.json', '--suite', 'data/commissioning_m4/suite.json', '--docker-image', image, '--results-dir', str(evidence/'native')]
run(sys.executable, 'run_evo.py', '--check-native', *common, log=evidence/'native-config.txt')
run(sys.executable, 'run_evo.py', '--native-seed', *common, log=evidence/'native-seed.txt')
run(sys.executable, 'scripts/report_m4.py', '--evidence', str(evidence), '--suite', 'data/commissioning_m4/suite.json', '--update-readme')
run(sys.executable, 'scripts/check_m4_continuity.py', '--output', str(evidence/'continuity.json'))
run(sys.executable, '-m', 'pip', 'freeze', log=evidence/'dependencies.txt')
shutil.copyfile('data/commissioning_m4/suite.json', evidence/'development-suite.json')
(evidence/'provenance.json').write_text(json.dumps({'source_commit': source_commit, 'delivery_commit': os.environ['GITHUB_SHA'], 'workflow_run': os.environ['GITHUB_RUN_ID'], 'docker_image_id': image, 'patch_sha256': hashlib.sha256(patch).hexdigest(), 'scope': 'Native contained development seed only. Zero model calls, evolved descendants, and research validation/test solver trials. Synthetic unit fixtures do not represent research holdouts.'}, indent=2)+'\n')
run('git', 'diff', '--check')
run('git', 'add', 'README.md', 'results/step4')
run('git', 'commit', '-m', 'Record native Docker M4 integration evidence and update scientific README')
remote = out('git', 'remote', 'get-url', 'origin')
assert remote in ('https://github.com/'+REPO, 'https://github.com/'+REPO+'.git'), remote
run('git', 'fetch', 'origin', BRANCH)
assert out('git', 'rev-parse', 'FETCH_HEAD') == os.environ['GITHUB_SHA'], 'branch advanced; do not overwrite concurrent work'
run('git', 'push', 'origin', 'HEAD:refs/heads/'+BRANCH)
print('PUBLISHED', out('git', 'rev-parse', 'HEAD'), flush=True)

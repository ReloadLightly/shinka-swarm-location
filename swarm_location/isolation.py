"""Opt-in Docker containment for the existing anytime protocol.

Only the ephemeral worker/code directory is mounted, read-only. A local image ID
must be resolved before a run. No automatic pulls, host network, repo mount,
provider credentials, Docker socket, added capabilities or privileged mode.
"""
from __future__ import annotations
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import uuid


def checked_image(image: str) -> str:
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
        raise ValueError('SWARM_DOCKER_IMAGE must be an immutable local sha256 image ID')
    return image


def command(work: Path, package: Path) -> tuple[list[str], str | None, dict]:
    image = os.environ.get('SWARM_DOCKER_IMAGE')
    if not image:
        return [sys.executable, '-I', '-u', str(package/'anytime_worker.py')], None, {'mode':'process'}
    checked_image(image)
    docker = shutil.which('docker')
    if docker is None:
        raise RuntimeError('Docker requested but docker executable is unavailable')
    if ',' in str(work):
        raise ValueError('Docker bind source cannot contain a comma')
    # A non-root container must traverse the ephemeral directory. No other host
    # directory is mounted, so this exposes only this trial's supplied code.
    work.chmod(0o755)
    package.chmod(0o755)
    for path in work.rglob('*.py'):
        path.chmod(0o444)
    memory_text = os.environ.get('SWARM_WORKER_MEMORY_MIB', '768')
    if not memory_text.isdecimal() or int(memory_text) < 1:
        raise ValueError('SWARM_WORKER_MEMORY_MIB must be a positive integer')
    memory_mib = int(memory_text)
    name = 'shinka-swarm-' + uuid.uuid4().hex
    argv = [docker,'run','--rm','--pull=never','--name',name,'--interactive',
        '--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges',
        '--user=65534:65534','--pids-limit=64',f'--memory={memory_mib}m',f'--memory-swap={memory_mib}m',
        '--cpus=1','--log-driver=none','--ulimit=nofile=128:128',
        '--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=32m,mode=1777',
        '--mount',f'type=bind,source={work},target=/work,readonly',
        '--workdir=/work',image,'python','-I','-B','-u','/work/swarm_location/anytime_worker.py']
    return argv,name,{'mode':'docker','image_id':image,'network':'none','user':'65534:65534',
        'read_only':True,'memory_mib':memory_mib,'cpus':1,'pids_limit':64}


def cleanup(name: str | None, env: dict) -> None:
    if name is None:
        return
    if not re.fullmatch(r'shinka-swarm-[a-f0-9]{32}', name):
        raise ValueError('refusing cleanup of an unrelated container')
    result = subprocess.run(['docker','rm','--force',name],env=env,
                            capture_output=True,timeout=30)
    if result.returncode and b'No such container' not in result.stderr:
        raise RuntimeError('Docker trial cleanup failed; inspect the named container')


def require_isolation(trusted_local=False, *, check_available=False):
    """Research entry points never silently downgrade generated code to a process."""
    image = os.environ.get('SWARM_DOCKER_IMAGE')
    if not image:
        if not trusted_local:
            raise ValueError('Docker isolation required; --trusted-local is only for explicitly trusted debugging')
        return {'mode': 'trusted-local-debug'}
    checked_image(image)
    if check_available:
        docker = shutil.which('docker')
        if docker is None:
            raise RuntimeError('Docker isolation required but docker executable is unavailable')
        result = subprocess.run([docker, 'image', 'inspect', '--format', '{{.Id}}', image],
                                capture_output=True, text=True, timeout=30)
        if result.returncode or result.stdout.strip() != image:
            raise RuntimeError('the pinned Docker image is not available locally; no process fallback')
    return {'mode': 'docker', 'image_id': image}

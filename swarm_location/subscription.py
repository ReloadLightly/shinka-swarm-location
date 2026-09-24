"""Subscription-only transport for the pinned native Headless/Codex provider.

This adapts the provider's command protocol, not its evolutionary loop. Auth stays
in the user's Codex installation. No OAuth tokens are read or used as API keys.
"""
from __future__ import annotations
import argparse
import asyncio
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

from .diagnostics import redact
from .persistence import atomic_json, exclusive, file_digest

EFFORTS = ('low', 'medium', 'high', 'xhigh')
ROOT = Path(__file__).resolve().parents[1]


def clean_env(source=None):
    """Keep local login discovery, but never inherit paid-provider credentials."""
    env = dict(os.environ if source is None else source)
    for key in list(env):
        upper = key.upper()
        if (any(x in upper for x in ('API_KEY', 'ACCESS_TOKEN', 'REFRESH_TOKEN', 'AUTH_TOKEN'))
                or upper.startswith(('OPENAI_', 'ANTHROPIC_', 'AZURE_', 'GOOGLE_', 'GEMINI_',
                                     'OPENROUTER_', 'DEEPSEEK_', 'AWS_', 'WANDB_', 'LITELLM_'))
                or upper in ('CODEX_API_KEY', 'GH_TOKEN', 'GITHUB_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN')):
            env.pop(key, None)
    # Native dotenv loaders must not repopulate paid keys from a repository .env.
    env['PYTHON_DOTENV_DISABLED'] = '1'
    env['SHINKA_PRICING_MODE'] = 'offline'
    # Local embedding requests must not follow an inherited corporate HTTP proxy.
    exclusions = env.get('NO_PROXY', env.get('no_proxy', '')).split(',')
    exclusions = list(dict.fromkeys([*(x for x in exclusions if x), '127.0.0.1', 'localhost', '::1']))
    env['NO_PROXY'] = env['no_proxy'] = ','.join(exclusions)
    return env


def model_route(model, effort):
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', model):
        raise ValueError('supply an explicit Codex model identifier available to your account')
    if effort not in EFFORTS:
        raise ValueError(f'unsupported Headless reasoning effort: {effort}')
    return f'headless/codex@{model}?effort={effort}'


def validate_route(route):
    match = re.fullmatch(r'headless/codex@([A-Za-z0-9][A-Za-z0-9._-]*)\?effort=(low|medium|high|xhigh)', route)
    if not match:
        raise ValueError('subscription mode accepts only explicit headless/codex@MODEL?effort=EFFORT routes')
    return route


def codex_prefix(binary=None, profile=None):
    result = [binary or os.environ.get('SWARM_CODEX_BINARY', 'codex')]
    profile = profile or os.environ.get('SWARM_CODEX_PROFILE')
    if profile:
        result += ['--profile', profile]
    result += ['-c', 'forced_login_method="chatgpt"', '-c', 'model_provider="openai"']
    return result


def check_auth(binary='codex', profile=None):
    resolved = shutil.which(binary)
    if not resolved:
        raise RuntimeError('Codex CLI is not installed on this host; install it and run codex login here')
    env = clean_env()
    version = subprocess.run([resolved, '--version'], capture_output=True, text=True,
                             timeout=30, env=env, check=True).stdout.strip()
    status_prefix = [resolved] + (['--profile', profile] if profile else [])
    status = subprocess.run(status_prefix + ['login', 'status'],
                            capture_output=True, text=True, timeout=30, env=env)
    text = status.stdout + '\n' + status.stderr
    if status.returncode or 'Logged in using ChatGPT' not in text:
        # Do not echo status: API-mode status may contain a masked or complete key.
        raise RuntimeError('ChatGPT-authenticated Codex login required; API-key auth is not accepted')
    return {'binary': str(Path(resolved).resolve()), 'version': version,
            'binary_sha256': file_digest(resolved), 'auth': 'chatgpt',
            'codex_home': str(Path(env.get('CODEX_HOME', str(Path.home()/'.codex'))).resolve()),
            'profile': profile, 'separately_billed_api_enabled': False}


def exec_command(binary, model, effort, output, profile=None):
    model_route(model, effort)
    return codex_prefix(binary, profile) + [
        '--ask-for-approval', 'never', 'exec', '--sandbox', 'read-only',
        '--skip-git-repo-check', '--ephemeral', '--json',
        '-c', f'model_reasoning_effort={json.dumps(effort)}',
        '-c', 'features.shell_tool=false', '-c', 'features.unified_exec=false',
        '-c', 'features.multi_agent=false', '-c', 'features.apps=false',
        '-c', 'features.memories=false', '-c', 'features.plugins=false', '-c', 'web_search="disabled"',
        '-c', 'mcp_servers={}', '-c', 'apps._default.enabled=false',
        '--model', model, '--output-last-message', str(output), '-']


def block(root, reason):
    atomic_json(Path(root)/'provider_blocked.json', {'reason': redact(reason), 'at_unix': time.time(),
                'action': 'No API fallback. Resolve the issue; explicitly resume with --resume-provider.'})


def parse_events(stdout):
    usage, failed = {}, []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get('type') == 'turn.completed':
            usage = event.get('usage') or {}
        elif event.get('type') in ('turn.failed', 'error'):
            failed.append(json.dumps(event))
    if failed:
        raise RuntimeError(redact('\n'.join(failed))[-8000:])
    if not usage:
        raise RuntimeError('Codex did not emit a completed-turn usage event')
    return {name: usage.get(name, 0) for name in
            ('input_tokens', 'cached_input_tokens', 'output_tokens', 'reasoning_tokens')}


def process_identity(pid):
    try:
        # Linux stat's comm may contain spaces; split only after the closing ')'.
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def cleanup_requests(root):
    for path in Path(root).glob('active_*.json'):
        try:
            data = json.loads(path.read_text())
        except FileNotFoundError:
            continue
        pid = data['pid']
        try:
            if (data['start'] is not None and process_identity(pid) == data['start']
                    and os.getpgid(pid) == pid):
                os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        path.unlink(missing_ok=True)


def query_cli(args):
    root = Path(os.environ['SWARM_SUBSCRIPTION_DIR']).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.agent != 'codex' or args.allow != 'read-only' or not args.usage:
        raise ValueError('this command supports only read-only Headless Codex with usage reporting')
    timeout = float(os.environ.get('SWARM_CODEX_TIMEOUT', '1800'))
    if not 0 < timeout < float(os.environ.get('SHINKA_HEADLESS_TIMEOUT', '1860')):
        raise ValueError('Codex timeout must be positive and shorter than native Headless timeout')
    model_route(args.model, args.reasoning_effort)
    prompt = Path(args.prompt_file).read_text()
    attempt = uuid.uuid4().hex
    record = {'attempt': attempt, 'model': args.model, 'effort': args.reasoning_effort,
              'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
              'billing': 'chatgpt_subscription', 'api_cost_usd': 0.0, 'started_unix': time.time()}
    with exclusive(root/'codex.lock'):
        if (root/'provider_blocked.json').exists():
            raise RuntimeError('Subscription provider is paused; no new request sent')
        proc = None
        old_handlers = {}
        try:
            # Check saved login before every request. This does not run inference.
            check_auth(os.environ['SWARM_CODEX_BINARY'], os.environ.get('SWARM_CODEX_PROFILE'))
            with tempfile.TemporaryDirectory(prefix='swarm-codex-') as directory:
                output = Path(directory)/'answer.txt'
                command = exec_command(os.environ['SWARM_CODEX_BINARY'], args.model,
                                       args.reasoning_effort, output)
                proc = subprocess.Popen(command, cwd=directory, env=clean_env(),
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True, start_new_session=True)
                atomic_json(root/f'active_{attempt}.json', {'pid': proc.pid, 'start': process_identity(proc.pid)})
                def interrupt(signum, frame):
                    raise InterruptedError(f'Codex request interrupted by signal {signum}')
                for sig in (signal.SIGTERM, signal.SIGINT):
                    old_handlers[sig] = signal.signal(sig, interrupt)
                stdout, stderr = proc.communicate(prompt, timeout=timeout)
                if proc.returncode:
                    raise RuntimeError(f'Codex exited {proc.returncode}: ' + redact(stderr or stdout)[-8000:])
                usage = parse_events(stdout)
                answer = output.read_text().strip() if output.exists() else ''
                if not answer:
                    raise RuntimeError('Codex returned no final answer')
                record.update(status='completed', usage=usage, completed_unix=time.time(),
                              answer_sha256=hashlib.sha256(answer.encode()).hexdigest())
                atomic_json(root/'usage'/f'{attempt}.json', record)
                print(answer)
                # The native provider's final-line protocol. Zero is marginal API
                # billing, NOT a claim of unlimited/free subscription consumption.
                print(json.dumps({'usage': {**usage, 'cost': 0.0, 'num_total_queries': 1}}))
        except BaseException as exc:
            record.update(status='provider_failed', completed_unix=time.time(), error=redact(str(exc)))
            atomic_json(root/'usage'/f'{attempt}.json', record)
            block(root, str(exc))
            raise
        finally:
            if proc is not None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
            (root/f'active_{attempt}.json').unlink(missing_ok=True)
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)


def cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('agent', nargs='?')
    parser.add_argument('--prompt-file')
    parser.add_argument('--work-dir')
    parser.add_argument('--allow', default='read-only')
    parser.add_argument('--usage', action='store_true')
    parser.add_argument('--model')
    parser.add_argument('--reasoning-effort')
    args = parser.parse_args(argv)
    if args.check:
        check_auth(os.environ.get('SWARM_CODEX_BINARY', 'codex'), os.environ.get('SWARM_CODEX_PROFILE'))
        print('ChatGPT-authenticated Codex available; no inference sent')
        return
    query_cli(args)


@contextmanager
def transport(args, resolved):
    """Install only process-local transport settings; never edit shared config."""
    saved = dict(os.environ)
    root = args.results_dir.resolve()/'subscription'
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.environ.clear()
        os.environ.update(clean_env(saved))
        auth = check_auth(args.codex_binary, args.codex_profile)
        os.environ.update(SWARM_CODEX_BINARY=auth['binary'], SWARM_SUBSCRIPTION_DIR=str(root),
            SWARM_CODEX_TIMEOUT=str(args.headless_timeout),
            SHINKA_HEADLESS_TIMEOUT=str(args.headless_timeout+90),
            SHINKA_HEADLESS_COMMAND=shlex.join([sys.executable, str(ROOT/'scripts/codex_headless.py')]))
        if args.codex_profile:
            os.environ['SWARM_CODEX_PROFILE'] = args.codex_profile
        else:
            os.environ.pop('SWARM_CODEX_PROFILE', None)
        paused = root/'provider_blocked.json'
        if paused.exists():
            if not args.resume_provider:
                raise RuntimeError('Provider paused; resolve quota/auth/runtime issue, then pass --resume-provider')
            paused.rename(root/f'provider_blocked_{time.time_ns()}.json')
        atomic_json(root/'auth_check.json', auth)
        yield auth
    finally:
        cleanup_requests(root)
        os.environ.clear()
        os.environ.update(saved)


async def run_with_pause(runner, root):
    """Supervise native run_async; leave sampling/evaluation/database to Shinka."""
    task = asyncio.create_task(runner.run_async())
    try:
        while not task.done():
            if (Path(root)/'provider_blocked.json').exists():
                cleanup_requests(root)
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise RuntimeError('Subscription provider paused. Evaluations remain resumable; no API fallback.')
            await asyncio.sleep(.1)
        await task
        if (Path(root)/'provider_blocked.json').exists():
            raise RuntimeError('Subscription provider paused; inspect subscription/provider_blocked.json')
    finally:
        if not task.done():
            cleanup_requests(root)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

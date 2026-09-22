"""Execute controlled containment/deadline probes; never evolutionary evidence."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from swarm_location.core import Instance
from swarm_location.anytime import run_anytime
from swarm_location.isolation import checked_image
from evaluate_anytime import write_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();checked_image(a.image)
    os.environ['SWARM_DOCKER_IMAGE']=a.image
    instance=Instance.from_dict({'schema_version':1,'name':'containment-unit-fixture',
        'nodes':[1,2,3,4],'edges':[[1,2,1],[1,3,1],[2,4,1],[3,4,1]],'od':[[1,4,10]]})
    with tempfile.TemporaryDirectory() as directory:
        work=Path(directory);canary=work/'host-only.txt';canary.write_text('controlled public canary')
        source=f'''import os, socket
from pathlib import Path

def solve(problem,k,seed,report,budget):
    assert os.getuid() == 65534
    assert not Path({str(canary)!r}).exists()
    assert not Path('/var/run/docker.sock').exists()
    assert 'OPENAI_API_KEY' not in os.environ
    status=Path('/proc/self/status').read_text()
    assert 'NoNewPrivs:\\t1' in status
    assert 'CapEff:\\t0000000000000000' in status
    try:
        Path('/work/candidate.py').write_text('forbidden')
    except OSError: pass
    else: raise AssertionError('writable supplied code')
    sock=socket.socket();sock.settimeout(.05)
    try:
        sock.connect(('192.0.2.1',443))
    except OSError: pass
    else: raise AssertionError('unexpected external connection')
    finally:sock.close()
    report([1]);return [1]
'''
        candidate=work/'probe.py';candidate.write_text(source)
        probe=run_anytime(instance,2,[.1,.5],program_path=candidate)
        if not probe['correct'] or probe['final_coverage'] != 1:
            write_json(a.output,{'probe':probe,'success':False})
            raise RuntimeError('controlled isolation probe failed')
        candidate.write_text('def solve(p,k,s,r,b):\n r([2])\n while True: pass\n')
        deadline=run_anytime(instance,2,[.1,.3],program_path=candidate)
        success=deadline['correct'] and deadline['termination']=='deadline' and deadline['final_coverage']==.5
        record={'scope':'Controlled synthetic security/protocol checks, not evolved programs',
            'success':success,'model_calls':0,'holdout_evaluations':0,
            'image_id':a.image,'checks':['nonroot','no host canary','no Docker socket','no provider environment',
                'read-only supplied code','no new privileges','no effective capabilities','no external connection',
                'deadline retains valid incumbent'], 'probe':probe,'deadline':deadline}
        write_json(a.output,record)
        if not success:raise RuntimeError('Docker deadline semantics failed')
    print(json.dumps({'success':True,'image_id':a.image,'model_calls':0},indent=2))

if __name__=='__main__':main()

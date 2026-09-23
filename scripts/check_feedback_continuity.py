"""Record M7 source changes explicitly while preserving all historical evidence."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluate_anytime import write_json
BASE='fc459b5cf56037005b69665f12a24b9e998e936e'
DECLARED={'evaluate_anytime.py','run_evo.py','campaign.py',
          'swarm_location/anytime.py','swarm_location/anytime_worker.py','swarm_location/isolation.py'}


def check():
    def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
    names=git('ls-tree','-r','--name-only',BASE).decode().splitlines()
    protected=[p for p in names if p.startswith(('configs/','results/','data/','swarm_location/'))
               or p in ('evaluate.py','evaluate_anytime.py','anytime_initial.py','initial.py','run_evo.py','campaign.py')]
    unchanged,changes={},{}
    for path in protected:
        old=git('show',BASE+':'+path);new=(ROOT/path).read_bytes()
        if old!=new:
            if path not in DECLARED:raise ValueError('undeclared change to scientific evidence/core: '+path)
            changes[path]={'before_sha256':hashlib.sha256(old).hexdigest(),'after_sha256':hashlib.sha256(new).hexdigest()}
        else:unchanged[path]=hashlib.sha256(old).hexdigest()
    old=git('show',BASE+':README.md').decode();new=(ROOT/'README.md').read_text()
    blocks=re.findall(r'<!-- ([A-Z0-9-]+):START -->',old)
    for b in blocks:
        a,z=f'<!-- {b}:START -->',f'<!-- {b}:END -->'
        if new.count(a)!=1 or new.count(z)!=1 or old.split(a)[1].split(z)[0]!=new.split(a)[1].split(z)[0]:
            raise ValueError('historical README evidence changed: '+b)
    return {'base_commit':BASE,'success':True,'unchanged_file_count':len(unchanged),
            'unchanged_sha256':unchanged,'declared_source_changes':changes,
            'historical_readme_blocks_unchanged':blocks,
            'timing_scope':'Receiver instrumentation changed; no assertion of timing equivalence or transfer of M5 guard'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=check();write_json(a.output,result)
    print({k:v for k,v in result.items() if k!='unchanged_sha256'})

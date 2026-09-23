"""Freeze a native development shortlist, then a validation-selected program.

No evolutionary operators are implemented here. This module only reads a completed
native SQLite population and independently evaluates frozen code on new networks.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from math import isfinite
from pathlib import Path
import sqlite3

from .suite import file_sha256
from .comparisons import comparison_spec, verify_comparison_evidence


def atomic_json(path: Path, data: dict):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    tmp.replace(path)


def snapshot_population(database: Path, directory: Path, seed_path: Path, limit: int=5) -> dict:
    """Run only after the native runner has exited. Deduplicate copies by code hash."""
    database,directory,seed_path=map(Path,(database,directory,seed_path))
    if not database.is_file() or not seed_path.is_file():
        raise ValueError('a real native database and its original seed are required')
    if type(limit) is not int or limit < 1:
        raise ValueError('positive shortlist size required')
    directory.mkdir(parents=True,exist_ok=True)
    frozen=directory/'population.sqlite'
    if frozen.exists() or (directory/'shortlist.json').exists():
        raise ValueError('shortlist already frozen; never replace it after validation')
    with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True) as original:
        with sqlite3.connect(frozen) as copy:
            original.backup(copy)
    with sqlite3.connect(frozen.resolve().as_uri()+'?mode=ro',uri=True) as connection:
        connection.row_factory=sqlite3.Row
        rows=[dict(row) for row in connection.execute(
            'SELECT id, code, generation, combined_score, correct, metadata FROM programs')]
    seed=seed_path.read_bytes(); seed_hash=hashlib.sha256(seed).hexdigest()
    pool={}
    valid_descendants=set()
    for row in rows:
        score=row['combined_score']
        if row['correct'] != 1 or not isinstance(score,(float,int)) or not isfinite(score):
            continue
        code=row['code'].encode('utf-8'); digest=hashlib.sha256(code).hexdigest()
        metadata=json.loads(row['metadata'] or '{}')
        island_copy=bool(metadata.get('island_copy') or metadata.get('is_island_copy'))
        if row['generation'] > 0 and digest != seed_hash and not island_copy:
            valid_descendants.add(digest)
        item={'sha256':digest,'code':code,'native_program_id':row['id'],
              'generation':row['generation'],'development_score':float(score)}
        if digest not in pool or score > pool[digest]['development_score']:
            pool[digest]=item
    if not valid_descendants:
        raise ValueError('no valid unique non-seed descendant; holdout selection remains unopened')
    ranked=sorted(pool.values(),key=lambda r:(-r['development_score'],r['sha256']))[:limit]
    if seed_hash not in {r['sha256'] for r in ranked}:
        ranked.append({'sha256':seed_hash,'code':seed,'native_program_id':None,
                       'generation':0,'development_score':None})
    candidates=[]
    for row in ranked:
        row=dict(row); code=row.pop('code')
        target=directory/'candidates'/(row['sha256']+'.py')
        target.parent.mkdir(exist_ok=True);target.write_bytes(code)
        row['path']=str(target.relative_to(directory))
        row['is_reference_seed']=row['sha256']==seed_hash
        candidates.append(row)
    record={'schema_version':1,'frozen_utc':datetime.now(timezone.utc).isoformat(),
        'population_sha256':file_sha256(frozen),'population_records':len(rows),
        'valid_unique_programs':len(pool),'valid_unique_nonseed_descendants':len(valid_descendants),
        'max_generation_observed':max(r['generation'] for r in rows),
        'rule':'top development combined_score, unique code; original seed always included',
        'limit':limit,'candidates':candidates,'validation_evaluations_before_freeze':0}
    atomic_json(directory/'shortlist.json',record)
    return record


def verify_shortlist(directory: Path) -> dict:
    directory=Path(directory)
    record=json.loads((directory/'shortlist.json').read_text())
    if record['valid_unique_nonseed_descendants'] < 1 or file_sha256(directory/'population.sqlite') != record['population_sha256']:
        raise ValueError('invalid or altered frozen native population')
    for row in record['candidates']:
        path=(directory/row['path']).resolve()
        if not path.is_relative_to(directory.resolve()) or file_sha256(path) != row['sha256']:
            raise ValueError('frozen candidate bytes changed or path escapes shortlist')
    return record


def freeze_champion(directory: Path, validation_suite: Path, evaluator, docker_image: str) -> dict:
    """Evaluator is supplied by the driver; real use calls unchanged coverage logic."""
    directory,validation_suite=map(Path,(directory,validation_suite))
    record=verify_shortlist(directory)
    manifest=directory/'champion.json'
    if manifest.exists():
        raise ValueError('champion already frozen; do not reselect after test access')
    validations=[]
    for row in record['candidates']:
        out=directory/'validation'/row['sha256']
        # Never silently recompute a completed validation measurement.
        if (out/'metrics.json').is_file() and (out/'correct.json').is_file():
            metrics=json.loads((out/'metrics.json').read_text())
        else:
            metrics=evaluator(directory/row['path'],out,validation_suite,'validation')
        verify_comparison_evidence(metrics, validation_suite, 'validation')
        correct=json.loads((out/'correct.json').read_text())['correct']
        if (metrics.get('private',{}).get('candidate_sha256') != row['sha256']
                or metrics.get('private',{}).get('suite_sha256') != file_sha256(validation_suite)
                or metrics.get('private',{}).get('docker_image_id') != docker_image):
            raise ValueError('validation evidence identity mismatch')
        metric=metrics.get('public',{}).get('mean_checkpoint_coverage_pct')
        if correct and (not isinstance(metric,(int,float)) or not isfinite(metric)):
            raise ValueError('non-finite validation coverage')
        validations.append({'sha256':row['sha256'],'path':row['path'],'correct':correct,
            'is_reference_seed':row['is_reference_seed'],'coverage_pct':metric,
            'metrics_path':str((out/'metrics.json').relative_to(directory)),
            'metrics_sha256':file_sha256(out/'metrics.json'),
            'correct_path':str((out/'correct.json').relative_to(directory)),
            'correct_sha256':file_sha256(out/'correct.json')})
    valid=[r for r in validations if r['correct']]
    if not valid:
        atomic_json(directory/'validation_failure.json',{'candidates':validations})
        raise ValueError('no valid validation result; test remains unopened')
    chosen=sorted(valid,key=lambda r:(-r['coverage_pct'],r['sha256']))[0]
    result={'schema_version':1,'frozen_utc':datetime.now(timezone.utc).isoformat(),
        'shortlist_sha256':file_sha256(directory/'shortlist.json'),
        'validation_suite_sha256':file_sha256(validation_suite),'docker_image_id':docker_image,
        'rule':'highest mean checkpoint coverage on validation; exact ties by code SHA-256',
        'selected':chosen,'validation_results':validations,'test_evaluations_before_freeze':0}
    spec = comparison_spec(json.loads(validation_suite.read_text()), 'validation')
    if spec is not None:
        result['comparison_profile'] = spec
    atomic_json(manifest,result)
    return result


def verify_champion(directory: Path) -> dict:
    directory=Path(directory);verify_shortlist(directory)
    result=json.loads((directory/'champion.json').read_text())
    if result['shortlist_sha256'] != file_sha256(directory/'shortlist.json'):
        raise ValueError('shortlist changed after champion selection')
    candidates=json.loads((directory/'shortlist.json').read_text())['candidates']
    selected = result['selected']
    if not any(c['sha256'] == selected['sha256'] and c['path'] == selected['path'] for c in candidates):
        raise ValueError('champion is not a frozen candidate')
    valid = [r for r in result['validation_results'] if r['correct']]
    if not valid or sorted(valid,key=lambda r:(-r['coverage_pct'],r['sha256']))[0] != selected:
        raise ValueError('champion does not follow the frozen validation rule')
    for row in result['validation_results']:
        for name in ('metrics','correct'):
            path=(directory/row[name+'_path']).resolve()
            if not path.is_relative_to(directory.resolve()) or file_sha256(path) != row[name+'_sha256']:
                raise ValueError('validation evidence changed after selection')
        if 'comparison_profile' in result:
            metrics = json.loads((directory/row['metrics_path']).read_text())
            if metrics.get('private', {}).get('comparison_profile') != result['comparison_profile']:
                raise ValueError('champion comparison identity differs from its validation evidence')
    return result


def evaluate_frozen_test(directory: Path,test_suite: Path,evaluator,docker_image: str) -> dict:
    directory,test_suite=map(Path,(directory,test_suite))
    champion=verify_champion(directory)
    if champion['docker_image_id'] != docker_image:
        raise ValueError('test executor image differs from validation')
    test_spec = comparison_spec(json.loads(test_suite.read_text()), 'test')
    validation_spec = champion.get('comparison_profile')
    if test_spec is not None or validation_spec is not None:
        if (test_spec is None or validation_spec is None
                or any(test_spec[key] != validation_spec[key] for key in test_spec if key != 'stage')):
            raise ValueError('test comparator profile differs from frozen validation')
    opened=directory/'test_opened.json'
    # An interrupted test is preserved rather than automatically repeated until
    # favorable timing appears. Any resumed assessment must be separately labelled.
    with opened.open('x') as f:
        json.dump({'champion_sha256':file_sha256(directory/'champion.json'),
                   'program_sha256':champion['selected']['sha256'],
                   'test_suite_sha256':file_sha256(test_suite),
                   'opened_utc':datetime.now(timezone.utc).isoformat()},f,indent=2)
    metrics=evaluator(directory/champion['selected']['path'],directory/'test',test_suite,'test')
    verify_comparison_evidence(metrics, test_suite, 'test')
    return metrics

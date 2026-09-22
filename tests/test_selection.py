"""Protocol unit tests use labelled synthetic DBs, never research descendants."""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from scripts.prepare_research import parse_documented, catalog_checked
from swarm_location.isolation import checked_image, command
from swarm_location.selection import (snapshot_population, verify_shortlist, freeze_champion,
                                     verify_champion, evaluate_frozen_test, atomic_json)
from swarm_location.suite import file_sha256

IMAGE='sha256:'+'a'*64

class HeaderTests(unittest.TestCase):
    net='<NUMBER OF NODES> 2\n<NUMBER OF LINKS> 1\n<FIRST THRU NODE> 1\n<END OF METADATA>\n1 2 100 1 1;\n'
    trips='<TOTAL OD FLOW> 5.000000000004\n<END OF METADATA>\nOrigin 1\n2 : 5;\n'
    tolerance={'absolute':'0.000000001','relative':'0.000000000001'}

    def test_bounded_header_roundoff_does_not_modify_od(self):
        data,note=parse_documented(self.net,self.trips,'tiny',self.tolerance)
        self.assertEqual(data['od'],[[1,2,5]])
        self.assertEqual(note['sum_minus_header'],'-0.000000000004')
        self.assertEqual(note['od_entries_modified'],0)
        self.assertFalse(note['source_bytes_modified'])

    def test_documented_comment_lines_are_not_demand(self):
        trips=self.trips.replace('Origin 1','~ header says 2 : 999; but this is a comment\nOrigin 1')
        data,note=parse_documented(self.net,trips,'tiny',self.tolerance)
        self.assertEqual(data['od'],[[1,2,5]])
        self.assertEqual(note['comment_lines_ignored'],1)

    def test_substantive_header_difference_fails(self):
        with self.assertRaises(ValueError):
            parse_documented(self.net,self.trips.replace('5.000000000004','6'),'tiny',self.tolerance)

    def test_unsupported_model_not_silently_repaired(self):
        with self.assertRaises(ValueError):
            parse_documented(self.net.replace('100 1 1;','100 1 0;'),self.trips,'tiny',self.tolerance)
        with self.assertRaises(ValueError):
            parse_documented(self.net,self.trips.replace('2 : 5;','1 : 5;'),'tiny',self.tolerance)

    def test_unparsed_demand_fails_even_with_good_total(self):
        with self.assertRaises(ValueError):
            parse_documented(self.net,self.trips+'garbage','tiny',self.tolerance)

    def test_source_family_and_topology_cannot_cross_splits(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'catalog.json'
            a={'id':'a','source_graph':'a','split':'development','files':{'network':{'git_blob_sha1':'1'*40}}}
            b={'id':'b','source_graph':'b','split':'test','files':{'network':{'git_blob_sha1':'1'*40}}}
            p.write_text(json.dumps({'schema_version':1,'datasets':[a,b]}))
            with self.assertRaises(ValueError):catalog_checked(p)
            b['files']['network']['git_blob_sha1']='2'*40;b['source_graph']='a'
            p.write_text(json.dumps({'schema_version':1,'datasets':[a,b]}))
            with self.assertRaises(ValueError):catalog_checked(p)

class IsolationTests(unittest.TestCase):
    def test_mutable_image_tag_rejected(self):
        for value in ['python:latest','python:3.11', 'sha256:123','--privileged']:
            with self.assertRaises(ValueError):checked_image(value)

    def test_docker_contract_no_host_secrets_mounts_or_network(self):
        with tempfile.TemporaryDirectory() as d:
            work=Path(d);package=work/'swarm_location';package.mkdir()
            (work/'candidate.py').write_text('pass')
            with patch.dict('os.environ',{'SWARM_DOCKER_IMAGE':IMAGE}),patch('shutil.which',return_value='/usr/bin/docker'):
                argv,name,metadata=command(work,package)
            for flag in ['--network=none','--read-only','--cap-drop=ALL','--user=65534:65534','--pull=never']:
                self.assertIn(flag,argv)
            self.assertEqual(argv.count('--mount'),1)
            self.assertNotIn('--privileged',argv)
            self.assertNotIn('-e',argv)
            self.assertEqual(metadata['mode'],'docker')
            self.assertEqual((work/'candidate.py').stat().st_mode & 0o777,0o444)

class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.seed=self.root/'seed.py';self.seed.write_text('# unit fixture seed\n')
        self.db=self.root/'unit-fixture.sqlite'
        with sqlite3.connect(self.db) as c:
            c.execute('CREATE TABLE programs (id TEXT,code TEXT,generation INTEGER,combined_score REAL,correct INTEGER,metadata TEXT)')
            c.executemany('INSERT INTO programs VALUES (?,?,?,?,?,?)',[
                ('seed',self.seed.read_text(),0,100,1,'{}'),
                ('a','# unit fixture a\n',1,110,1,'{}'),
                ('copy','# unit fixture a\n',2,110,1,'{"island_copy":true}'),
                ('b','# unit fixture b\n',2,109,1,'{}'),
                ('bad','# incorrect fixture\n',3,200,0,'{}')])
        self.out=self.root/'selection'
        self.validation=self.root/'validation.json';self.validation.write_text('{"unit_fixture":true}')
        self.test=self.root/'test.json';self.test.write_text('{"unit_fixture":true}')
        self.calls=[]

    def tearDown(self):self.tmp.cleanup()

    def fake_evaluator(self,program,output,suite,split):
        """Only unit-testing freeze logic. Never used by the real campaign."""
        self.calls.append((file_sha256(program),split))
        score=95 if 'fixture b' in Path(program).read_text() else 85
        result={'public':{'mean_checkpoint_coverage_pct':score},'private':{
            'candidate_sha256':file_sha256(program),'suite_sha256':file_sha256(suite),'docker_image_id':IMAGE}}
        atomic_json(Path(output)/'metrics.json',result)
        atomic_json(Path(output)/'correct.json',{'correct':True})
        return result

    def freeze(self):return snapshot_population(self.db,self.out,self.seed,2)

    def test_native_copies_are_deduplicated_and_seed_included(self):
        record=self.freeze()
        self.assertEqual(record['valid_unique_nonseed_descendants'],2)
        self.assertEqual(len(record['candidates']),3)
        self.assertEqual(sum(c['is_reference_seed'] for c in record['candidates']),1)
        self.assertEqual(self.calls,[])

    def test_no_valid_descendants_does_not_open_holdout(self):
        with sqlite3.connect(self.db) as c:c.execute('DELETE FROM programs WHERE generation > 0')
        with self.assertRaises(ValueError):self.freeze()
        self.assertFalse((self.out/'shortlist.json').exists())
        self.assertEqual(self.calls,[])

    def test_frozen_candidate_change_detected(self):
        record=self.freeze();(self.out/record['candidates'][0]['path']).write_text('altered')
        with self.assertRaises(ValueError):verify_shortlist(self.out)

    def test_select_on_validation_not_development_then_open_test_once(self):
        self.freeze();record=freeze_champion(self.out,self.validation,self.fake_evaluator,IMAGE)
        self.assertIn('fixture b',(self.out/record['selected']['path']).read_text())
        self.assertEqual([s for _,s in self.calls],['validation']*3)
        evaluate_frozen_test(self.out,self.test,self.fake_evaluator,IMAGE)
        self.assertEqual(self.calls[-1][1],'test')
        with self.assertRaises(FileExistsError):evaluate_frozen_test(self.out,self.test,self.fake_evaluator,IMAGE)
        self.assertEqual(len(self.calls),4)

    def test_validation_reselection_refused_after_freeze(self):
        self.freeze();freeze_champion(self.out,self.validation,self.fake_evaluator,IMAGE)
        with self.assertRaises(ValueError):freeze_champion(self.out,self.validation,self.fake_evaluator,IMAGE)

    def test_changed_validation_artifact_or_champion_path_fails(self):
        self.freeze();record=freeze_champion(self.out,self.validation,self.fake_evaluator,IMAGE)
        path=self.out/'champion.json';record['selected']['path']='../outside.py';atomic_json(path,record)
        with self.assertRaises(ValueError):verify_champion(self.out)

    def test_test_image_change_refused(self):
        self.freeze();freeze_champion(self.out,self.validation,self.fake_evaluator,IMAGE)
        with self.assertRaises(ValueError):evaluate_frozen_test(self.out,self.test,self.fake_evaluator,'sha256:'+'b'*64)
        self.assertFalse((self.out/'test_opened.json').exists())

    def test_validation_image_identity_checked(self):
        self.freeze()
        with self.assertRaises(ValueError):freeze_champion(self.out,self.validation,self.fake_evaluator,'sha256:'+'b'*64)

if __name__=='__main__':unittest.main()

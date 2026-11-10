"""Exercise fake SSH preparation across separate processes, with default deadlines."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]

class FakePreparationTests(unittest.TestCase):
    def test_start_status_idempotency_and_backup_failure(self):
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory(dir=ROOT) as tmp:
                node = Path(tmp) / 'lax'; node.mkdir()
                identity = {'node_id': 'n', 'instance_id': 'i'}
                (node/'state.json').write_text(json.dumps({'node':identity}))
                (node/'users.json').write_text('{"users":[]}')
                (node/'config.toml').write_text('# fixture\n')
                (node/'VERSION').write_text('0.5.0')
                env = dict(os.environ, VCL_FAKE_STATE_DIR=tmp)
                if fail:
                    env['VCL_FAKE_FAIL_BACKUP']='lax'
                else:
                    env.pop('VCL_FAKE_FAIL_BACKUP', None)
                op = str(uuid.uuid4())
                binding = dict(identity, source_version='0.5.0',payload_sha256='a'*64)
                def invoke(action, extra=()):
                    result=subprocess.run([sys.executable,str(ROOT/'tests/fixtures/fake-ssh'),
                        'root@203.0.113.10','--','python3','/stage/lib/upgrade_prepare.py',action,op,*extra],
                        env=env,capture_output=True,text=True,timeout=10)
                    self.assertEqual(result.returncode,0,result.stderr)
                    return json.loads(result.stdout)
                args=['--binding',json.dumps(binding),'--helper','/stage/bin/vincula','--seconds','900']
                first=invoke('start',args)
                self.assertEqual(first['state'],'RUNNING')
                final=invoke('status')
                self.assertEqual(final['state'],'FAILED' if fail else 'SUCCEEDED', final)
                self.assertEqual(final['binding'],binding)
                self.assertEqual(invoke('start',args),final)
                if fail:
                    self.assertEqual(final['phase'],'backup')
                    self.assertFalse((node/'upgrade-checkpoints').exists())
                else:
                    self.assertTrue(final['backup']['ok'])
                    self.assertTrue(final['checkpoint']['ok'])
                    self.assertEqual(len(list((node/'upgrade-checkpoints').glob('upgrade-checkpoint-*'))),1)
                self.assertEqual((node/'VERSION').read_text(),'0.5.0')

if __name__ == '__main__':
    unittest.main()

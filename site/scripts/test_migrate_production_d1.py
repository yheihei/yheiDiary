import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('migrate_production_d1.py')
spec = importlib.util.spec_from_file_location('diary_migrate', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
NAMES = json.loads((SCRIPT.parents[1] / '.emdash/migrations.json').read_text())['migrationSet']['names']


def report():
    return {'target': {'kind': 'd1', 'label': m.TARGET_LABEL, 'accountId': m.ACCOUNT, 'resourceId': m.DATABASE,
                       'fingerprint': m.FINGERPRINT},
            'knownApplied': NAMES[:40], 'pending': NAMES[40:], 'unknownApplied': [],
            'executed': [], 'lock': {'id': m.LOCK_ID, 'heldSince': m.LOCK_SINCE}}


class SafetyChecks(unittest.TestCase):
    def test_expected_target_and_state(self):
        m.validate_report(report(), NAMES, expect_pending=True)
        changed = report()
        changed['target']['resourceId'] = 'different-database'
        with self.assertRaises(m.StopMigration):
            m.validate_report(changed, NAMES, expect_pending=True)
        changed = report()
        changed['knownApplied'] = NAMES[:41]
        with self.assertRaises(m.StopMigration):
            m.validate_report(changed, NAMES, expect_pending=True)
        changed = report()
        changed['lock']['id'] = 'another-lock'
        with self.assertRaises(m.StopMigration):
            m.validate_report(changed, NAMES, expect_pending=True)

    def test_official_json_stdout_with_target_diagnostics_on_stderr(self):
        dummy = 'cfat_dummy-secret-for-test-long-enough'
        expected = report()
        fake = subprocess.CompletedProcess([], 0, stdout=json.dumps(expected),
                                           stderr='Migration target: d1 account/database\nTarget fingerprint: fixture\n')
        with patch.object(m.subprocess, 'run', return_value=fake):
            actual = m.cli(dummy, '--status', '--json')
        self.assertEqual(actual, expected)
        m.validate_report(actual, NAMES, expect_pending=True)

    def test_json_report_must_have_required_fields_and_correct_types(self):
        with self.assertRaises(m.StopMigration):
            m.parse_report(json.dumps(report()) + '\nMigration target: diagnostics')
        for bad in ({'target': {}}, {**report(), 'pending': 'not-an-array'},
                    {**report(), 'lock': {'id': 123, 'heldSince': m.LOCK_SINCE}}):
            with self.assertRaises(m.StopMigration):
                m.parse_report(json.dumps(bad))

    def test_worker_must_be_exact_paused_version(self):
        good = [{'created_on': '2026-10-25T10:51:42Z', 'versions': [
            {'version_id': m.PAUSE_VERSION, 'percentage': 100}]}]
        m.validate_deployments(good)
        bad = [{'created_on': '2026-10-25T10:52:42Z', 'versions': [
            {'version_id': 'different-version', 'percentage': 100}]}]
        with self.assertRaises(m.StopMigration):
            m.validate_deployments(good + bad)

    def test_cli_error_redacts_dummy_secret(self):
        dummy = 'cfat_dummy-secret-for-test-long-enough'
        fake = subprocess.CompletedProcess([], 1, stdout='error ' + dummy, stderr='')
        with patch.object(m.subprocess, 'run', return_value=fake):
            with self.assertRaises(m.StopMigration) as caught:
                m.cli(dummy, '--status', '--json')
        self.assertNotIn(dummy, str(caught.exception))
        self.assertIn('[redacted]', str(caught.exception))

    def test_prompt_does_not_echo_dummy_secret(self):
        pid, fd = pty.fork()
        if pid == 0:
            os.execv(sys.executable, [sys.executable, '-u', str(SCRIPT), '--self-test'])
        output = b''
        deadline = time.monotonic() + 8
        try:
            while b'Dummy secret' not in output and time.monotonic() < deadline:
                if select.select([fd], [], [], 0.2)[0]:
                    output += os.read(fd, 4096)
            self.assertIn(b'Dummy secret', output)
            os.write(fd, b'dummy-secret-for-test\n')
            while time.monotonic() < deadline:
                if select.select([fd], [], [], 0.2)[0]:
                    try: output += os.read(fd, 4096)
                    except OSError: break
            _, status = os.waitpid(pid, 0)
            self.assertEqual(os.waitstatus_to_exitcode(status), 0)
            self.assertIn(b'SELF TEST ONLY', output)
            self.assertNotIn(b'dummy-secret-for-test', output)
        finally:
            os.close(fd)


if __name__ == '__main__':
    unittest.main()

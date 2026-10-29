import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit
import build
import release

class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_corrupt_download_cache_is_rejected(self):
        (self.root / 'source').write_bytes(b'corrupt')
        with patch.object(build, 'CACHE', self.root), self.assertRaisesRegex(ValueError, 'checksum'):
            build.download({'url': 'https://invalid.example/', 'sha256': '0' * 64}, 'source')

    def test_foreign_elf_is_rejected_before_host_tool_execution(self):
        path = self.root / 'library'
        path.write_bytes(b'\x7fELF\x02\x01\x01\x00' + bytes(64))
        with patch.object(audit.subprocess, 'check_output') as tool, self.assertRaisesRegex(ValueError, 'Scarlet'):
            audit.audit(path)
        tool.assert_not_called()

    def test_symbolic_flag_and_tls_are_rejected(self):
        path = self.root / 'library'
        data = bytearray(64); data[:8] = b'\x7fELF\x02\x01\x01\x53'
        struct.pack_into('<HH', data, 16, 3, 183); path.write_bytes(data)
        for output in ('  TLS 0x0000\n', '  0x1e (FLAGS) SYMBOLIC\n', '  0x1 (NEEDED) libc.so.6\n'):
            with patch.object(audit.subprocess, 'check_output', return_value=output), self.assertRaises(ValueError):
                audit.audit(path)

    def test_modified_payload_is_rejected(self):
        (self.root / 'file').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'payload'):
            release.verify(self.root, {'files': {'file': '0' * 64}})

    def test_glfw_accepts_only_shared_sws_and_verified_imports(self):
        path = self.root / 'library'
        data = bytearray(64); data[:8] = b'\x7fELF\x02\x01\x01\x53'
        struct.pack_into('<HH', data, 16, 3, 183); path.write_bytes(data)
        exports = '\n'.join('T ' + s for s in ('glfwInit', 'glfwCreateWindow', 'glfwCreateWindowSurface', 'glfwPollEvents'))
        needed = '  0x1 (NEEDED) Shared library: [libsws_client_c.so]\n'
        with patch.object(audit.subprocess, 'check_output', side_effect=[needed, 'U sws_poll_event\n', exports]):
            self.assertEqual(audit.audit(path, 'glfw')['imports'], ['sws_poll_event'])
        for dependencies in ('', needed.replace('libsws_client_c.so', 'libc.so.6'), needed + needed):
            with patch.object(audit.subprocess, 'check_output', return_value=dependencies), self.assertRaisesRegex(ValueError, 'dependencies'):
                audit.audit(path, 'glfw')
        with patch.object(audit.subprocess, 'check_output', side_effect=[needed, 'U internal_unresolved_helper\n']), self.assertRaisesRegex(ValueError, 'Unverified'):
            audit.audit(path, 'glfw')
        with patch.object(audit.subprocess, 'check_output', side_effect=[needed, '', exports + '\nT sws_poll_event']), self.assertRaisesRegex(ValueError, 'exports'):
            audit.audit(path, 'glfw')

    def test_development_build_cannot_be_published(self):
        receipt = self.root / 'build.json'
        for fields in ({'local_source': True}, {'local_source': False, 'producer_dirty': True}):
            receipt.write_text(json.dumps(fields))
            with self.assertRaisesRegex(ValueError, 'clean producer'):
                release.package(receipt, 'v0.1.1', self.root / 'release')

if __name__ == '__main__': unittest.main()

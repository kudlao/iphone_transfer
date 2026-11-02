"""USB discovery regression tests. No device is required."""
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from iphone_usb import AFCCommandLine, AFCError, list_iphone_media


class FakeAFC:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def listdir(self, path, cancelled=None):
        if path == '/':
            return ['DCIM']
        if path == '/DCIM':
            return ['100APPLE']
        if path == '/DCIM/100APPLE':
            return ['IMG_%04d.HEIC' % n for n in range(30)]
        return []


class ScanTests(unittest.TestCase):
    def test_completed_scan(self):
        with mock.patch('iphone_usb.open_afc', return_value=FakeAFC()):
            items = list_iphone_media()
        self.assertEqual(len(items), 30)

    def test_cancellation_is_not_reported_as_complete(self):
        cancelled = threading.Event()
        events = []

        def batch(items, count):
            events.append(count)
            cancelled.set()

        with mock.patch('iphone_usb.open_afc', return_value=FakeAFC()):
            with self.assertRaises(InterruptedError):
                list_iphone_media(on_batch=batch, cancelled=cancelled, batch_size=1)
        self.assertEqual(events, [1])

    def test_disconnected_phone_ends_scan_with_error(self):
        class Unplugged(FakeAFC):
            def listdir(self, path, cancelled=None):
                if path == '/DCIM/100APPLE':
                    raise AFCError('iPhone disconnected')
                return super().listdir(path, cancelled)
        with mock.patch('iphone_usb.open_afc', return_value=Unplugged()):
            with self.assertRaisesRegex(AFCError, 'disconnected'):
                list_iphone_media()

    def test_idevice_id_detects_unplug(self):
        # Keep the fake executable visible throughout both probes.
        # Patching only __init__ caused _ensure_connected to skip both probes:
        # on the test machine idevice_id.exe is not physically installed.
        with mock.patch('iphone_usb.Path.is_file', return_value=True), \
             mock.patch('iphone_usb.subprocess.run', side_effect=[
                 SimpleNamespace(returncode=0, stdout=b'PHONE-ID\n'),
                 SimpleNamespace(returncode=0, stdout=b'')
             ]) as command:
            client = AFCCommandLine('C:/native/afcclient.exe')
            client._ensure_connected()
            client._last_probe = -100
            with self.assertRaisesRegex(AFCError, 'отключён'):
                client._ensure_connected()
            self.assertEqual(command.call_count, 2)

    def test_missing_idevice_probe_does_not_bypass_cancel(self):
        with mock.patch('iphone_usb.Path.is_file', return_value=True):
            client = AFCCommandLine('C:/native/afcclient.exe')
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(InterruptedError):
            client._ensure_connected(cancelled)


if __name__ == '__main__':
    unittest.main()

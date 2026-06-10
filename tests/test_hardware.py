import unittest

from app.hardware import HardwareAccelerationStatus, resolve_whisper_runtime


class HardwareRuntimeTests(unittest.TestCase):

    def test_auto_prefers_cuda_when_available(self):
        status = HardwareAccelerationStatus("Windows", True, 1, True, [], True, "CUDA available")
        self.assertEqual(resolve_whisper_runtime("auto", "auto", status), ("cuda", "float16"))

    def test_auto_falls_back_to_cpu_int8_without_cuda(self):
        status = HardwareAccelerationStatus("Windows", False, 0, False, [], False, "No CUDA")
        self.assertEqual(resolve_whisper_runtime("auto", "auto", status), ("cpu", "int8"))

    def test_explicit_device_is_respected(self):
        status = HardwareAccelerationStatus("Windows", True, 1, True, [], True, "CUDA available")
        self.assertEqual(resolve_whisper_runtime("cpu", "auto", status), ("cpu", "int8"))

    def test_auto_uses_cpu_when_cuda_runtime_is_missing(self):
        status = HardwareAccelerationStatus("Windows", False, 1, False, ["cublas64_12.dll"], True, "CUDA DLL missing")
        self.assertEqual(resolve_whisper_runtime("auto", "auto", status), ("cpu", "int8"))

    def test_windows_cuda_requires_cudnn_runtime(self):
        from unittest import mock
        from app import hardware

        with mock.patch.object(hardware.platform, "system", return_value="Windows"), \
             mock.patch.object(hardware, "_dll_exists_on_path", return_value=True), \
             mock.patch.object(hardware, "_dll_pattern_exists_on_path", return_value=False):
            ready, missing = hardware._cuda_runtime_status("Windows")

        self.assertFalse(ready)
        self.assertIn("cudnn*.dll", missing)



if __name__ == "__main__":
    unittest.main()

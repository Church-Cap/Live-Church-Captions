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


class HardwareStatusMessageTests(unittest.TestCase):

    def test_status_dict_includes_clear_cuda_fields(self):
        status = HardwareAccelerationStatus(
            "Windows",
            False,
            0,
            False,
            ["cublas64_12.dll"],
            True,
            "CUDA not ready",
            nvidia_driver_status="detected",
            nvidia_gpu_names=["Example NVIDIA GPU"],
            ctranslate2_cuda_status="not_exposed",
            cuda_runtime_status="missing_dlls",
            fallback_mode="CPU / int8",
        )
        data = status.as_dict()
        self.assertEqual(data["nvidia_driver_status"], "detected")
        self.assertEqual(data["nvidia_gpu_names"], ["Example NVIDIA GPU"])
        self.assertEqual(data["ctranslate2_cuda_status"], "not_exposed")
        self.assertEqual(data["cuda_runtime_status"], "missing_dlls")
        self.assertEqual(data["fallback_mode"], "CPU / int8")


class MacHardwareReportingTests(unittest.TestCase):

    def test_status_dict_can_include_mac_fields(self):
        status = HardwareAccelerationStatus(
            "Darwin",
            False,
            0,
            True,
            [],
            False,
            "Apple Mac detected",
            apple_chip="Apple M2 Pro",
            apple_gpu_names=["Apple M2 Pro"],
            mac_model="Mac14,9",
            cpu_brand="Apple M2 Pro",
            physical_cpu_count=10,
            performance_core_count=6,
            efficiency_core_count=4,
        )
        data = status.as_dict()
        self.assertEqual(data["apple_chip"], "Apple M2 Pro")
        self.assertEqual(data["apple_gpu_names"], ["Apple M2 Pro"])
        self.assertEqual(data["performance_core_count"], 6)

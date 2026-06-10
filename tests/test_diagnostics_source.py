import ast
import pathlib
import unittest


class DiagnosticsSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = pathlib.Path("app/main.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        for node in cls.tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "diagnostics_payload":
                cls.payload_source = ast.get_source_segment(cls.source, node) or ""
                break
        else:
            raise AssertionError("diagnostics_payload was not found")

    def test_diagnostics_route_exists(self):
        self.assertIn('"/api/diagnostics/export"', self.source)
        self.assertIn("diagnostics_payload", self.source)

    def test_diagnostics_payload_avoids_transcript_and_secret_sources(self):
        for forbidden in ("settings.operator_password", "settings.session_secret", "hub.final_segments", "segments_to_json", "CONFIG_PATH", "os.environ"):
            self.assertNotIn(forbidden, self.payload_source)

    def test_diagnostics_route_requires_confirmation(self):
        self.assertIn('request.query_params.get("confirmed") != "1"', self.source)
        self.assertIn("confirmation_required", self.source)

    def test_operator_has_diagnostics_menu_section(self):
        operator = pathlib.Path("app/templates/operator.html").read_text(encoding="utf-8")
        self.assertIn('data-section="diagnostics"', operator)
        self.assertIn('id="operator-section-diagnostics"', operator)
        self.assertIn("/operator#diagnostics", pathlib.Path("app/templates/feedback.html").read_text(encoding="utf-8"))

    def test_diagnostics_public_sharing_warning_exists(self):
        operator = pathlib.Path("app/templates/operator.html").read_text(encoding="utf-8")
        feedback = pathlib.Path("app/templates/feedback.html").read_text(encoding="utf-8")
        self.assertIn("Do not post the file publicly on GitHub", operator)
        self.assertIn("Do not post the file publicly on GitHub", feedback)
        self.assertIn("do not post it publicly on GitHub", self.source)

    def test_cuda_log_path_uses_relative_label(self):
        self.assertIn('CUDA_RUNTIME_LOG_LABEL = "logs/cuda-runtime-install.log"', self.source)
        self.assertNotIn('"log": str(PROJECT_ROOT / "logs" / "cuda-runtime-install.log")', self.source)
        self.assertNotIn('return {"pid": process.pid, "log": str(log_path)}', self.source)

    def test_redaction_helper_exists(self):
        self.assertIn("def _redact_local_paths", self.source)
        self.assertIn("<home>", self.source)
        self.assertIn("<project_root>", self.source)

    def test_system_specs_are_included(self):
        self.assertIn("def _system_specs_snapshot", self.source)
        self.assertIn("total_memory_gib", self.source)
        self.assertIn("project_drive_free_gib", self.source)
        self.assertIn('"system": _system_specs_snapshot()', self.payload_source)


if __name__ == "__main__":
    unittest.main()

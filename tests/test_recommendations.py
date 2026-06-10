import ast
import pathlib
import unittest


class RecommendationSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = pathlib.Path("app/main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "recommended_performance_config":
                cls.function_source = ast.get_source_segment(source, node) or ""
                break
        else:
            raise AssertionError("recommended_performance_config was not found")

    def test_recommendations_do_not_auto_apply_medium_model(self):
        self.assertNotIn('"performance_preset": "most_accurate"', self.function_source)
        self.assertNotIn('"whisper_model": "medium.en"', self.function_source)

    def test_recommendations_keep_balanced_cuda_on_faster_whisper(self):
        self.assertIn('"performance_preset": "balanced"', self.function_source)
        self.assertIn('"transcriber_mode": "faster_whisper"', self.function_source)
        self.assertIn('"whisper_model": "base.en"', self.function_source)


if __name__ == "__main__":
    unittest.main()

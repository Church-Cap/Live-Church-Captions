import importlib
import os
import tempfile
import unittest
from pathlib import Path


class DeploymentProfileTests(unittest.TestCase):
    def setUp(self):
        self.original_env = {
            key: os.environ.get(key)
            for key in (
                "CHURCHCAP_DEPLOYMENT",
                "CHURCHCAP_PROFILE",
                "CHURCHCAP_APPLIANCE_ID",
                "CHURCHCAP_LANGUAGE_MODE",
                "CHURCHCAP_APPLIANCE_IDENTITY_FILE",
            )
        }
        for key in self.original_env:
            os.environ.pop(key, None)
        self.identity_dir = tempfile.TemporaryDirectory()
        os.environ["CHURCHCAP_APPLIANCE_IDENTITY_FILE"] = str(Path(self.identity_dir.name) / "missing-identity.json")

    def tearDown(self):
        self.identity_dir.cleanup()
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def reload_deployment(self):
        import app.deployment as deployment

        module = importlib.reload(deployment)
        module.load_deployment_identity.cache_clear()
        return module

    def test_desktop_profile_is_default(self):
        deployment = self.reload_deployment()

        context = deployment.deployment_context({"cuda_available": False})

        self.assertFalse(context["identity"]["mode"] == "appliance")
        self.assertEqual(context["capabilities"]["profile"], "desktop")
        self.assertTrue(context["capabilities"]["show_model_slider"])
        self.assertTrue(context["capabilities"]["allow_translation"])

    def test_cpu_appliance_shows_language_page_but_blocks_translation_until_enabled(self):
        os.environ["CHURCHCAP_DEPLOYMENT"] = "appliance"
        os.environ["CHURCHCAP_PROFILE"] = "appliance_cpu"
        deployment = self.reload_deployment()

        context = deployment.deployment_context({"cuda_available": True})

        self.assertEqual(context["identity"]["mode"], "appliance")
        self.assertEqual(context["capabilities"]["profile"], "appliance_cpu")
        self.assertTrue(context["capabilities"]["show_translation_setup"])
        self.assertFalse(context["capabilities"]["allow_translation"])
        self.assertTrue(context["capabilities"]["translation_advanced"])
        self.assertTrue(context["capabilities"]["cpu_translation_available"])
        self.assertFalse(context["capabilities"]["cpu_translation_enabled"])
        self.assertTrue(context["capabilities"]["cpu_translation_requires_confirmation"])
        self.assertEqual(context["capabilities"]["translation_max_limit"], 3)

    def test_cpu_appliance_can_opt_in_to_limited_cpu_translation(self):
        os.environ["CHURCHCAP_DEPLOYMENT"] = "appliance"
        os.environ["CHURCHCAP_PROFILE"] = "appliance_cpu"
        os.environ["CHURCHCAP_LANGUAGE_MODE"] = "cpu_limited"
        deployment = self.reload_deployment()

        context = deployment.deployment_context({"cuda_available": False})

        self.assertTrue(context["capabilities"]["show_translation_setup"])
        self.assertTrue(context["capabilities"]["allow_translation"])
        self.assertTrue(context["capabilities"]["translation_advanced"])
        self.assertEqual(context["capabilities"]["translation_max_limit"], 3)

    def test_gpu_appliance_requires_cuda_for_translation(self):
        os.environ["CHURCHCAP_DEPLOYMENT"] = "appliance"
        os.environ["CHURCHCAP_PROFILE"] = "appliance_gpu"
        deployment = self.reload_deployment()

        waiting = deployment.deployment_context({"cuda_available": False})
        ready = deployment.deployment_context({"cuda_available": True})

        self.assertTrue(waiting["capabilities"]["show_translation_setup"])
        self.assertFalse(waiting["capabilities"]["allow_translation"])
        self.assertTrue(ready["capabilities"]["allow_translation"])

    def test_identity_file_activates_appliance_explicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            identity = Path(tmp) / "identity.json"
            identity.write_text(
                '{"appliance": true, "profile": "appliance_cpu", "appliance_id": "box-test"}',
                encoding="utf-8",
            )
            os.environ["CHURCHCAP_APPLIANCE_IDENTITY_FILE"] = str(identity)
            deployment = self.reload_deployment()

            context = deployment.deployment_context({"cuda_available": False})

        self.assertEqual(context["identity"]["appliance_id"], "box-test")
        self.assertEqual(context["capabilities"]["profile"], "appliance_cpu")


if __name__ == "__main__":
    unittest.main()

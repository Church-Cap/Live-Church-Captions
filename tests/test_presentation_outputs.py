from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import main
from app.broadcast import CaptionHub
from app.transcript_store import TranscriptStore


class PresentationOutputTests(unittest.TestCase):
    def test_obs_and_display_receive_public_language_context(self):
        public_state = {
            "enabled": True,
            "available_languages": ["en", "fr"],
            "language_policy": "automatic",
            "language_requests_enabled": True,
            "requestable_languages": [],
            "language_requests": [],
            "translated_audio": {"enabled": False},
        }
        with patch.object(main, "public_translation_state", return_value=public_state):
            client = TestClient(main.app)
            for path in ("/obs?lang=fr&integration=propresenter", "/propresenter?lang=fr", "/display?lang=fr"):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("window.CC_LANGUAGES", response.text)
                self.assertIn("window.CC_TRANSLATION_STATE", response.text)
                self.assertIn('"available_languages":["en","fr"]', response.text.replace(" ", ""))
                self.assertNotIn('"resources"', response.text)
                self.assertNotIn('"scheduler"', response.text)

    def test_propresenter_overlay_alias_is_public_and_reports_as_propresenter(self):
        self.assertTrue(main.is_public_viewer_path("/propresenter"))
        self.assertTrue(main.is_public_viewer_path("/obs"))
        self.assertFalse(main.is_public_viewer_path("/propresenter/help"))
        self.assertFalse(main.is_public_viewer_path("/obs/help"))
        client = TestClient(main.app)
        alias = client.get("/propresenter?lang=en")
        overlay = client.get("/obs?lang=en&integration=propresenter")
        self.assertEqual(alias.status_code, 200)
        self.assertIn('class="obs-page"', alias.text)
        self.assertEqual(alias.text, overlay.text)
        source = Path("app/static/client.js").read_text(encoding="utf-8")
        self.assertIn("requestedIntegration === 'propresenter' || location.pathname === '/propresenter'", source)

    def test_presentation_language_is_url_selected_and_role_is_explicit(self):
        source = Path("app/static/client.js").read_text(encoding="utf-8")
        language_resolution = source.split("const presentationParameters", 1)[1].split("let pendingCurrentText", 1)[0]
        self.assertIn("presentationRequestedLanguage || SOURCE_LANGUAGE", language_resolution)
        self.assertIn("localStorage.getItem('captionLanguage') || navigator.language", language_resolution)
        self.assertIn("isPresentationPage", language_resolution)
        self.assertIn("if (!isPresentationPage && !isOperatorPage) localStorage.setItem('captionLanguage'", source)
        self.assertIn("captionSocketParameters.set('role', 'presentation')", source)
        self.assertIn("captionSocketParameters.set('presentation', presentationKind)", source)

    def test_presentation_pages_do_not_enable_spoken_translation(self):
        source = Path("app/static/client.js").read_text(encoding="utf-8")
        self.assertIn("let translationAudioEnabled = false", source)
        self.assertIn("if (!translationAudioEnabled", source)

    def test_websocket_route_tracks_propresenter_without_counting_a_viewer(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            hub = CaptionHub(
                transcript_store=TranscriptStore(
                    encrypted_path=root / "transcript.json.enc",
                    key_path=root / "transcript.key",
                    plaintext_fallback_path=root / "transcript.json",
                )
            )
            with patch.object(main, "hub", hub):
                client = TestClient(main.app)
                with client.websocket_connect(
                    "/ws/captions?lang=en&role=presentation&presentation=propresenter"
                ) as websocket:
                    self.assertEqual(websocket.receive_json()["type"], "state")
                    viewer_meta = websocket.receive_json()
                    self.assertEqual(viewer_meta["type"], "viewer_meta")
                    self.assertEqual(viewer_meta["viewers"], 0)
                    self.assertNotIn("presentation_connections", viewer_meta["data"])
                    self.assertEqual(hub.viewer_count, 0)
                    self.assertEqual(
                        hub.presentation_connections()["by_kind"],
                        {"propresenter": 1},
                    )
                self.assertEqual(hub.presentation_connections()["total"], 0)

    def test_websocket_route_tracks_room_display_language_without_counting_a_viewer(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            hub = CaptionHub(
                transcript_store=TranscriptStore(
                    encrypted_path=root / "transcript.json.enc",
                    key_path=root / "transcript.key",
                    plaintext_fallback_path=root / "transcript.json",
                )
            )
            with patch.object(main, "hub", hub):
                client = TestClient(main.app)
                with client.websocket_connect(
                    "/ws/captions?lang=fr&role=presentation&presentation=room-display"
                ) as websocket:
                    self.assertEqual(websocket.receive_json()["type"], "state")
                    self.assertEqual(websocket.receive_json()["type"], "viewer_meta")
                    self.assertEqual(hub.viewer_count, 0)
                    self.assertEqual(
                        hub.presentation_connections()["by_kind"],
                        {"room-display": 1},
                    )
                    self.assertEqual(
                        hub.presentation_connections()["languages_by_kind"],
                        {"room-display": {"fr": 1}},
                    )
                self.assertEqual(hub.presentation_connections()["total"], 0)

    def test_operator_caption_preview_is_a_non_counted_english_observer(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            hub = CaptionHub(
                transcript_store=TranscriptStore(
                    encrypted_path=root / "transcript.json.enc",
                    key_path=root / "transcript.key",
                    plaintext_fallback_path=root / "transcript.json",
                )
            )
            with patch.object(main, "hub", hub):
                client = TestClient(main.app)
                with client.websocket_connect("/ws/captions?lang=en&role=operator") as websocket:
                    self.assertEqual(websocket.receive_json()["type"], "state")
                    self.assertEqual(websocket.receive_json()["viewers"], 0)
                    self.assertEqual(hub.viewer_count, 0)
                    self.assertEqual(hub.translation_demand_counts(), {})
                    self.assertEqual(hub.presentation_connections()["total"], 0)


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from starlette.requests import Request

from app import main, runtime_config
from app.broadcast import CaptionHub
from app.i18n import LANGUAGE_BY_CODE, LocalTranslator, TranslationResult
from app.models import CaptionSegment
from app.source_language import SOURCE_LANGUAGES, source_model, validate_source_language
from app.transcript_store import TranscriptStore


def request(body):
    async def receive():
        return {"type": "http.request", "body": json.dumps(body).encode()}
    return Request({"type": "http", "method": "POST", "path": "/api/source-language", "headers": []}, receive)


class SourceLanguageTests(unittest.TestCase):
    def test_catalogue_is_understood_by_caption_routing(self):
        self.assertTrue(set(SOURCE_LANGUAGES) <= set(LANGUAGE_BY_CODE))

    def test_preserves_model_size_and_english_defaults(self):
        for size in ("tiny", "base", "small", "medium"):
            self.assertEqual(source_model(size + ".en", "sv"), size)
            self.assertEqual(source_model(size + ".en", "en"), size + ".en")
            self.assertEqual(source_model(size, "sv"), size)

    def test_invalid_language_is_rejected(self):
        for value in (None, [], "auto", "xx", "SV", "sv-SE"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_source_language(value)

    def test_every_performance_preset_uses_multilingual_weights_for_swedish(self):
        with patch.object(main.hub, "source_language", "sv"):
            for preset in main.PERFORMANCE_PRESETS:
                config = main.effective_performance_config({"performance_preset": preset})
                self.assertFalse(config["whisper_model"].endswith('.en'))

    def test_swedish_reaches_both_transcribers_without_english_prompt(self):
        for mode, module, name in (
            ('whisper', 'app.transcription.whisper_live', 'WhisperLiveTranscriber'),
            ('faster_whisper', 'app.transcription.faster_whisper_live', 'FasterWhisperTranscriber'),
        ):
            config = main.effective_performance_config({"performance_preset": "balanced", "transcriber_mode": mode})
            config['whisper_model'] = 'base'
            with patch.object(main.hub, 'source_language', 'sv'), patch.object(main, 'effective_performance_config', return_value=config), patch(f'{module}.{name}') as constructor:
                main.create_transcriber()
                self.assertEqual(constructor.call_args.kwargs['language'], 'sv')
                self.assertEqual(constructor.call_args.kwargs['model_name'], 'base')
                self.assertIsNone(constructor.call_args.kwargs['initial_prompt'])

    def test_invalid_stored_language_falls_back(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runtime_config, 'CONFIG_PATH', Path(directory) / 'config.json'):
            runtime_config.CONFIG_PATH.write_text('{"source_language": "invalid"}')
            self.assertIsNone(runtime_config.load_runtime_config()['source_language'])


class SourceLanguageAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.hub = CaptionHub(transcript_store=TranscriptStore(Path(self.directory.name) / 'history.json'))

    async def test_switch_persists_clears_old_feed_and_notifies_viewers(self):
        ws = AsyncMock()
        await self.hub.connect(ws, language='en')
        await self.hub.publish(CaptionSegment(text='Old English caption', is_final=True))
        with patch.object(main, 'hub', self.hub), patch.object(main, 'captions_are_running', return_value=False), patch.object(runtime_config, 'CONFIG_PATH', Path(self.directory.name) / 'config.json'):
            result = await main.set_source_language_api(request({'source_language': 'sv'}))
            self.assertEqual(result['source_language'], 'sv')
            self.assertEqual(runtime_config.load_runtime_config()['source_language'], 'sv')
            self.assertEqual(result['performance']['whisper_model'], 'base')
        self.assertEqual(self.hub.source_language, 'sv')
        self.assertEqual(self.hub.translator.source_language, 'sv')
        self.assertEqual(self.hub._clients[ws], 'sv')
        self.assertIsNone(self.hub.state().current)
        self.assertEqual(self.hub.state().history, [])
        self.assertIn({'type': 'source_language', 'language': 'sv'}, [call.args[0] for call in ws.send_json.call_args_list])
        self.assertEqual(self.hub.translation_state()['source_language'], 'sv')
        await self.hub.publish(CaptionSegment(text='Välkommen till vår gudstjänst.', is_final=True))
        self.assertEqual(self.hub.state().current.text, 'Välkommen till vår gudstjänst.')
        await self.hub.change_source_language('en')
        self.assertEqual(self.hub._clients[ws], 'en')

    async def test_change_during_captions_is_rejected_without_saving(self):
        with patch.object(main, 'captions_are_running', return_value=True), patch.object(main, 'save_runtime_config') as save:
            response = await main.set_source_language_api(request({'source_language': 'sv'}))
            self.assertEqual(response.status_code, 409)
            save.assert_not_called()

    async def test_invalid_input_is_rejected_without_saving(self):
        with patch.object(main, 'captions_are_running', return_value=False), patch.object(main, 'save_runtime_config') as save:
            response = await main.set_source_language_api(request({'source_language': 'xx'}))
            self.assertEqual(response.status_code, 400)
            save.assert_not_called()

    async def test_english_is_a_translation_target_for_swedish_source(self):
        self.hub.source_language = 'sv'
        self.hub.configure_translation(enabled=True, provider='demo', allowed_languages=['sv', 'en'], max_active_languages=2)
        ws = AsyncMock()
        await self.hub.connect(ws, language='en')
        self.hub.translator = LocalTranslator('sv')
        segment = CaptionSegment(text='Välkommen', is_final=True)
        with patch.object(self.hub.translator, 'cached_result', return_value=TranslationResult(text='Welcome', applied=True)):
            self.assertEqual(self.hub._translate_segment_for_language(segment, 'en').text, 'Welcome')
            self.assertEqual(self.hub._translate_segment_for_language(segment, 'sv').text, 'Välkommen')

    async def test_english_only_tigrinya_provider_is_not_used_for_swedish(self):
        translator = LocalTranslator('sv')
        with patch.object(translator, '_translate_with_opus_tigrinya') as opus:
            await translator.translate_async('Välkommen', 'ti', enabled=True, provider='argos')
            opus.assert_not_called()

    async def test_viewer_surfaces_render_the_selected_source(self):
        scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""}
        with patch.object(main.hub, 'source_language', 'sv'):
            for render in (main.index, main.display, main.obs_overlay):
                response = await render(Request(scope))
                self.assertIn('window.CC_SOURCE_LANGUAGE = "sv"', response.body.decode())

    async def test_custom_multilingual_model_and_manual_targets_survive_save(self):
        with patch.object(runtime_config, 'CONFIG_PATH', Path(self.directory.name) / 'config.json'):
            runtime_config.save_runtime_config({'source_language': 'sv', 'whisper_model': 'small', 'translation_allowed_languages': ['de']})
            stored = runtime_config.load_runtime_config()
            self.assertEqual(stored['whisper_model'], 'small')
            self.assertIn('sv', stored['translation_allowed_languages'])
            self.assertNotIn('en', stored['translation_allowed_languages'])

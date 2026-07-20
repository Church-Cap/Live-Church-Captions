import re
import unittest
from pathlib import Path

from app.localisation import (
    get_client_ui_coverage,
    get_client_ui_language_strings,
    get_client_ui_sources,
    validate_client_ui_catalog,
)
from app.i18n import SUPPORTED_LANGUAGES


class ClientUiStringTests(unittest.TestCase):
    def test_catalog_is_internally_complete(self):
        self.assertEqual(validate_client_ui_catalog(), [])

    def test_finnish_ui_strings_are_static(self):
        sources = get_client_ui_sources(["fi"])
        strings = get_client_ui_language_strings("fi")
        english = get_client_ui_language_strings("en")

        self.assertEqual(sources["fi"], "static")
        self.assertEqual(strings["live_captions"], "Livetekstitys")
        self.assertNotEqual(strings["waiting"], english["waiting"])

    def test_catalog_covers_every_supported_caption_language(self):
        codes = [language["code"] for language in SUPPORTED_LANGUAGES]
        coverage = get_client_ui_coverage(codes)
        missing_static = [code for code in codes if not coverage[code]]

        self.assertTrue(coverage["en"])
        self.assertTrue(coverage["fi"])
        self.assertTrue(coverage["ast"])
        self.assertEqual(missing_static, [])

    def test_non_english_static_locales_are_not_plain_english_copies(self):
        english = get_client_ui_language_strings("en")
        codes = [language["code"] for language in SUPPORTED_LANGUAGES if language["code"] != "en"]
        static_codes = [code for code, source in get_client_ui_sources(codes).items() if source == "static"]

        self.assertTrue(static_codes)
        self.assertEqual(
            [code for code in static_codes if get_client_ui_language_strings(code) == english],
            [],
        )

    def test_unsupported_ui_language_uses_english_fallback(self):
        sources = get_client_ui_sources(["zz"])
        strings = get_client_ui_language_strings("zz")
        english = get_client_ui_language_strings("en")

        self.assertEqual(sources["zz"], "fallback")
        self.assertEqual(strings["live_captions"], english["live_captions"])

    def test_caption_template_i18n_keys_exist_in_english(self):
        template = Path("app/templates/captions.html").read_text(encoding="utf-8")
        keys = set(re.findall(r'data-i18n(?:-[\\w-]+)?="([^"]+)"', template))
        english = get_client_ui_language_strings("en")

        self.assertTrue(keys)
        self.assertEqual(sorted(keys - set(english)), [])

    def test_client_flags_keep_language_code_fallback_visible(self):
        styles = Path("app/static/styles.css").read_text(encoding="utf-8")

        self.assertIn(".language-flag-chip::after", styles)
        self.assertIn("content: attr(data-code);", styles)
        self.assertIn(".phone-page .language-flag-chip::after", styles)
        self.assertNotIn("content: none;", styles)

    def test_client_refreshes_language_metadata_when_picker_opens(self):
        script = Path("app/static/client.js").read_text(encoding="utf-8")

        self.assertIn("async function refreshLanguageMetadata", script)
        self.assertIn("fetch('/api/languages'", script)
        self.assertIn("refreshLanguageMetadata();", script)

    def test_sensitive_moment_message_uses_client_ui_language_key(self):
        english = get_client_ui_language_strings("en")
        spanish = get_client_ui_language_strings("es")
        script = Path("app/static/client.js").read_text(encoding="utf-8")
        broadcast = Path("app/broadcast.py").read_text(encoding="utf-8")

        self.assertIn("sensitive_paused_message", english)
        self.assertIn("sensitive_resumed_message", english)
        self.assertNotEqual(spanish["sensitive_paused_message"], english["sensitive_paused_message"])
        self.assertIn("payload.message_key", script)
        self.assertIn("showSystemMessageFromKey", script)
        self.assertIn("state.sensitive_mode", script)
        self.assertIn("ensureLanguageUiStrings(viewerLanguage, {showLoading: false})", script)
        self.assertIn("const uiStringRequests = new Map();", script)
        self.assertIn("return uiStringRequests.get(code)", script)
        self.assertNotIn("{showNotice: true}", script)
        self.assertIn("\"message_key\": \"sensitive_paused_message\"", broadcast)

    def test_live_caption_card_allows_draft_after_existing_final_lines(self):
        script = Path("app/static/client.js").read_text(encoding="utf-8")

        self.assertIn("const draftItems = currentDraftText", script)
        self.assertNotIn("const draftItems = !finalItems.length && currentDraftText", script)
        self.assertIn("wordDelta >= 2", script)

    def test_transcript_history_preserves_reader_content_when_new_items_arrive(self):
        script = Path("app/static/client.js").read_text(encoding="utf-8")

        self.assertIn("history.scrollTop = previousScrollTop + Math.max(0, history.scrollHeight - previousScrollHeight);", script)

    def test_live_feed_is_viewport_bounded_and_scrolls_internally(self):
        styles = Path("app/static/styles.css").read_text(encoding="utf-8")

        self.assertIn(".phone-page {\n  height: 100dvh;", styles)
        self.assertIn(".phone-page .phone-shell {\n  height: 100dvh;", styles)
        self.assertIn("overflow-y: auto;", styles)
        self.assertIn(".phone-page .current-caption::before", styles)

    def test_live_feed_keeps_a_scroll_buffer_and_follows_only_at_the_bottom(self):
        script = Path("app/static/client.js").read_text(encoding="utf-8")

        self.assertIn("renderLines: isPhonePage", script)
        self.assertIn("slice(-limits.renderLines)", script)
        self.assertIn("const shouldFollowLive = distanceFromBottom <= 32;", script)
        self.assertIn("current.scrollTop = current.scrollHeight;", script)

    def test_english_uses_source_units_in_the_same_accumulated_live_reader(self):
        script = Path("app/static/client.js").read_text(encoding="utf-8")
        broadcast = Path("app/broadcast.py").read_text(encoding="utf-8")

        self.assertIn("function applyLiveSourceUpdates(items)", script)
        self.assertIn("payload.language === SOURCE_LANGUAGE", script)
        self.assertIn("applyLiveSourceUpdates(payload.live_source_updates)", script)
        self.assertIn("live_source_updates=source_units", broadcast)
        self.assertIn('"live_source_updates": [', broadcast)

    def test_live_source_revisions_replace_the_existing_line(self):
        script = Path("app/static/client.js").read_text(encoding="utf-8")
        template = Path("app/templates/captions.html").read_text(encoding="utf-8")

        self.assertIn("let currentDraftUnitId = null;", script)
        self.assertIn("id: `${currentDraftUnitId || 'draft'}:stream:${index}`", script)
        self.assertIn("const existingIndex = finalSegments.findIndex(item => item.id === key);", script)
        self.assertIn("finalSegments[existingIndex] = nextFinal;", script)
        self.assertIn("if (!seg.is_final && !hasLiveSourceUpdates && !currentDraftText && !finalSegments.length)", script)
        self.assertIn("else if (seg.is_final && !hasLiveSourceUpdates && !finalSegments.length)", script)
        self.assertIn("segment.cue_id || segment.source_unit_id", script)
        self.assertIn("segment.cue_revision || segment.source_revision", script)
        self.assertIn('/static/client.js?v=0.7.0-responsive-context-1', template)

    def test_live_draft_extensions_keep_existing_line_breaks(self):
        script = Path("app/static/client.js").read_text(encoding="utf-8")
        styles = Path("app/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("function extendDraftLines(previousText, previousLines, nextText, maxChars)", script)
        self.assertIn("function reviseMutableDraftTail(previousText, previousLines, nextText, stableWordCount, maxChars)", script)
        self.assertIn("function captionLineWidthLimit()", script)
        self.assertIn("captionMeasureContext.measureText(text).width <= maxPixels", script)
        self.assertIn("? extendDraftLines(previousDraftText, currentDraftLines, displayText, limits.chars)", script)
        self.assertIn("if (isPresentationPage && !suppressSubtitleGlideOnce) animateSubtitleGlide(previousRects);", script)
        self.assertIn("seg.layoutChars !== limits.chars", script)
        self.assertIn("id: `${key}:stream:${index}`", script)
        self.assertIn(".phone-page .subtitle-line", styles)
        self.assertIn("transition: opacity 180ms ease", styles)
        self.assertNotIn("MIN_PARTIAL_UPDATE_MS", script)

    def test_session_transcript_starts_closed_with_matching_button_state(self):
        template = Path("app/templates/captions.html").read_text(encoding="utf-8")
        script = Path("app/static/client.js").read_text(encoding="utf-8")

        self.assertRegex(
            template,
            r'<button id="toggleTranscript"[^>]+data-i18n="show_transcript"[^>]+aria-expanded="false"',
        )
        self.assertRegex(template, r'<section[^>]+id="historyWrap" hidden>')
        self.assertIn("let transcriptVisible = false;", script)
        self.assertNotIn("localStorage.getItem('captionTranscriptVisible')", script)
        self.assertNotIn("localStorage.setItem('captionTranscriptVisible'", script)

    def test_dismissing_notices_expands_the_shared_viewer_layout(self):
        template = Path("app/templates/captions.html").read_text(encoding="utf-8")
        script = Path("app/static/client.js").read_text(encoding="utf-8")
        english = get_client_ui_language_strings("en")
        farsi = get_client_ui_language_strings("fa")
        simplified_chinese = get_client_ui_language_strings("zh-hans")
        traditional_chinese = get_client_ui_language_strings("zh-hant")

        self.assertIn("data-dismiss-viewer-notice", template)
        self.assertNotIn("onclick=\"document.getElementById('dndNotice').remove()\"", template)
        self.assertIn("function syncViewerNoticeLayout()", script)
        self.assertIn("viewer-notices-visible", script)
        self.assertIn("close_notices_hint", english)
        self.assertNotEqual(farsi["close_notices_hint"], english["close_notices_hint"])
        self.assertNotEqual(simplified_chinese["close_notices_hint"], english["close_notices_hint"])
        self.assertNotEqual(traditional_chinese["close_notices_hint"], english["close_notices_hint"])
        self.assertNotEqual(
            simplified_chinese["live_captions"],
            traditional_chinese["live_captions"],
        )


if __name__ == "__main__":
    unittest.main()

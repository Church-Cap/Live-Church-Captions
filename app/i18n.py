from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SOURCE_LANGUAGE = "en"

SUPPORTED_LANGUAGES: list[dict[str, str]] = [
    {"code": "en", "name": "English", "native": "English", "flag": "🇬🇧", "dir": "ltr"},
    {"code": "es", "name": "Spanish", "native": "Español", "flag": "🇪🇸", "dir": "ltr"},
    {"code": "fr", "name": "French", "native": "Français", "flag": "🇫🇷", "dir": "ltr"},
    {"code": "pt", "name": "Portuguese", "native": "Português", "flag": "🇵🇹", "dir": "ltr"},
    {"code": "pl", "name": "Polish", "native": "Polski", "flag": "🇵🇱", "dir": "ltr"},
    {"code": "uk", "name": "Ukrainian", "native": "Українська", "flag": "🇺🇦", "dir": "ltr"},
    {"code": "ar", "name": "Arabic", "native": "العربية", "flag": "🇸🇦", "dir": "rtl"},
    {"code": "fa", "name": "Farsi", "native": "فارسی", "flag": "🇮🇷", "dir": "rtl"},
]

LANGUAGE_BY_CODE = {item["code"]: item for item in SUPPORTED_LANGUAGES}

CLIENT_UI_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "live_captions": "Live captions",
        "current": "Current",
        "recent_captions": "Recent captions",
        "newest_first": "Newest first",
        "live_updates": "Live text updates automatically",
        "waiting": "Waiting for captions…",
        "dnd_title": "Do Not Disturb",
        "dnd_text": "Consider turning on Do Not Disturb so notifications do not distract you and you can focus on the Word of God.",
        "ai_notice_title": "AI caption notice",
        "ai_notice_text": "Captions are generated automatically and may be inaccurate at times. Please check with the speaker or church team if something seems unclear.",
        "translation_notice_title": "Experimental translation",
        "translation_notice_text": "Translated captions are experimental and may be inaccurate or unavailable. Scripture, names, theology, and pastoral details should be checked with the church team.",
        "language": "Language",
        "theme": "Theme",
        "comfort": "Comfort",
        "compact": "Compact",
        "pause": "Pause",
        "resume": "Resume",
        "clear": "Clear",
        "live": "Live",
        "reconnecting": "Reconnecting",
        "connection_issue": "Connection issue",
        "translation_not_available": "Translation is not available for this caption; showing the source language.",
    },
    "es": {
        "live_captions": "Subtítulos en vivo", "current": "Actual", "recent_captions": "Subtítulos recientes", "newest_first": "Más recientes primero", "live_updates": "El texto se actualiza automáticamente", "waiting": "Esperando subtítulos…", "dnd_title": "No molestar", "dnd_text": "Considera activar No molestar para evitar distracciones y poder concentrarte en la Palabra de Dios.", "ai_notice_title": "Aviso sobre subtítulos de IA", "ai_notice_text": "Los subtítulos se generan automáticamente y pueden ser inexactos. Consulta con el equipo de la iglesia si algo no está claro.", "translation_notice_title": "Traducción experimental", "translation_notice_text": "Los subtítulos traducidos son experimentales y pueden ser inexactos o no estar disponibles. Verifica Escritura, nombres, teología y detalles pastorales con la iglesia.", "language": "Idioma", "theme": "Tema", "comfort": "Cómodo", "compact": "Compacto", "pause": "Pausar", "resume": "Reanudar", "clear": "Borrar", "live": "En vivo", "reconnecting": "Reconectando", "connection_issue": "Problema de conexión", "translation_not_available": "La traducción no está disponible para este subtítulo; se muestra el idioma original."
    },
    "fr": {
        "live_captions": "Sous-titres en direct", "current": "Actuel", "recent_captions": "Sous-titres récents", "newest_first": "Les plus récents d’abord", "live_updates": "Le texte se met à jour automatiquement", "waiting": "En attente des sous-titres…", "dnd_title": "Ne pas déranger", "dnd_text": "Pensez à activer Ne pas déranger pour éviter les notifications et vous concentrer sur la Parole de Dieu.", "ai_notice_title": "Avis sur les sous-titres IA", "ai_notice_text": "Les sous-titres sont générés automatiquement et peuvent être inexacts. Vérifiez avec l’équipe de l’église si quelque chose semble flou.", "translation_notice_title": "Traduction expérimentale", "translation_notice_text": "Les sous-titres traduits sont expérimentaux et peuvent être inexacts ou indisponibles. Vérifiez les Écritures, les noms, la théologie et les détails pastoraux avec l’église.", "language": "Langue", "theme": "Thème", "comfort": "Confort", "compact": "Compact", "pause": "Pause", "resume": "Reprendre", "clear": "Effacer", "live": "En direct", "reconnecting": "Reconnexion", "connection_issue": "Problème de connexion", "translation_not_available": "La traduction n’est pas disponible pour ce sous-titre ; affichage de la langue source."
    },
    "pt": {
        "live_captions": "Legendas ao vivo", "current": "Atual", "recent_captions": "Legendas recentes", "newest_first": "Mais recentes primeiro", "live_updates": "O texto é atualizado automaticamente", "waiting": "Aguardando legendas…", "dnd_title": "Não perturbe", "dnd_text": "Considere ativar Não perturbe para evitar notificações e focar na Palavra de Deus.", "ai_notice_title": "Aviso de legendas por IA", "ai_notice_text": "As legendas são geradas automaticamente e podem conter erros. Fale com a equipa da igreja se algo não estiver claro.", "translation_notice_title": "Tradução experimental", "translation_notice_text": "Legendas traduzidas são experimentais e podem ser imprecisas ou indisponíveis. Confirme Escritura, nomes, teologia e detalhes pastorais com a igreja.", "language": "Idioma", "theme": "Tema", "comfort": "Conforto", "compact": "Compacto", "pause": "Pausar", "resume": "Retomar", "clear": "Limpar", "live": "Ao vivo", "reconnecting": "Reconectando", "connection_issue": "Problema de ligação", "translation_not_available": "A tradução não está disponível para esta legenda; mostrando o idioma original."
    },
    "pl": {
        "live_captions": "Napisy na żywo", "current": "Aktualne", "recent_captions": "Ostatnie napisy", "newest_first": "Najnowsze najpierw", "live_updates": "Tekst aktualizuje się automatycznie", "waiting": "Oczekiwanie na napisy…", "dnd_title": "Nie przeszkadzać", "dnd_text": "Rozważ włączenie trybu Nie przeszkadzać, aby skupić się na Słowie Bożym.", "ai_notice_title": "Informacja o napisach AI", "ai_notice_text": "Napisy są generowane automatycznie i czasem mogą być niedokładne. W razie niejasności zapytaj zespół kościoła.", "translation_notice_title": "Tłumaczenie eksperymentalne", "translation_notice_text": "Tłumaczone napisy są eksperymentalne i mogą być niedokładne lub niedostępne. Sprawdź Pismo, imiona, teologię i kwestie duszpasterskie z kościołem.", "language": "Język", "theme": "Motyw", "comfort": "Wygodny", "compact": "Kompaktowy", "pause": "Pauza", "resume": "Wznów", "clear": "Wyczyść", "live": "Na żywo", "reconnecting": "Ponowne łączenie", "connection_issue": "Problem z połączeniem", "translation_not_available": "Tłumaczenie nie jest dostępne; wyświetlany jest język źródłowy."
    },
    "uk": {
        "live_captions": "Субтитри наживо", "current": "Поточне", "recent_captions": "Останні субтитри", "newest_first": "Найновіші спочатку", "live_updates": "Текст оновлюється автоматично", "waiting": "Очікування субтитрів…", "dnd_title": "Не турбувати", "dnd_text": "Увімкніть режим Не турбувати, щоб не відволікатися й зосередитися на Божому Слові.", "ai_notice_title": "Попередження про AI-субтитри", "ai_notice_text": "Субтитри створюються автоматично й іноді можуть бути неточними. Якщо щось незрозуміло, зверніться до команди церкви.", "translation_notice_title": "Експериментальний переклад", "translation_notice_text": "Перекладені субтитри експериментальні й можуть бути неточними або недоступними. Перевіряйте Писання, імена, богослов’я та пасторські деталі з командою церкви.", "language": "Мова", "theme": "Тема", "comfort": "Зручний", "compact": "Компактний", "pause": "Пауза", "resume": "Продовжити", "clear": "Очистити", "live": "Наживо", "reconnecting": "Повторне з’єднання", "connection_issue": "Проблема з’єднання", "translation_not_available": "Переклад недоступний; показано мову оригіналу."
    },
    "ar": {
        "live_captions": "تعليقات مباشرة", "current": "الحالي", "recent_captions": "التعليقات الأخيرة", "newest_first": "الأحدث أولاً", "live_updates": "يتم تحديث النص تلقائياً", "waiting": "في انتظار التعليقات…", "dnd_title": "عدم الإزعاج", "dnd_text": "فكّر في تشغيل عدم الإزعاج حتى لا تشتتك الإشعارات وتركز على كلمة الله.", "ai_notice_title": "تنبيه تعليقات الذكاء الاصطناعي", "ai_notice_text": "يتم إنشاء التعليقات تلقائياً وقد تكون غير دقيقة أحياناً. اسأل فريق الكنيسة إذا كان شيء غير واضح.", "translation_notice_title": "ترجمة تجريبية", "translation_notice_text": "التعليقات المترجمة تجريبية وقد تكون غير دقيقة أو غير متاحة. تحقق من النصوص والأسماء واللاهوت والتفاصيل الرعوية مع فريق الكنيسة.", "language": "اللغة", "theme": "المظهر", "comfort": "مريح", "compact": "مضغوط", "pause": "إيقاف", "resume": "استئناف", "clear": "مسح", "live": "مباشر", "reconnecting": "إعادة الاتصال", "connection_issue": "مشكلة اتصال", "translation_not_available": "الترجمة غير متاحة لهذا التعليق؛ يتم عرض لغة المصدر."
    },
    "fa": {
        "live_captions": "زیرنویس زنده", "current": "فعلی", "recent_captions": "زیرنویس‌های اخیر", "newest_first": "جدیدترین‌ها اول", "live_updates": "متن به‌طور خودکار به‌روزرسانی می‌شود", "waiting": "در انتظار زیرنویس…", "dnd_title": "مزاحم نشوید", "dnd_text": "حالت مزاحم نشوید را روشن کنید تا اعلان‌ها حواس شما را پرت نکند و بر کلام خدا تمرکز کنید.", "ai_notice_title": "اطلاعیه زیرنویس هوش مصنوعی", "ai_notice_text": "زیرنویس‌ها خودکار تولید می‌شوند و ممکن است گاهی نادرست باشند. اگر چیزی نامشخص بود با تیم کلیسا بررسی کنید.", "translation_notice_title": "ترجمه آزمایشی", "translation_notice_text": "زیرنویس‌های ترجمه‌شده آزمایشی هستند و ممکن است نادرست یا در دسترس نباشند. کتاب‌مقدس، نام‌ها، الهیات و موارد شبانی را با تیم کلیسا بررسی کنید.", "language": "زبان", "theme": "ظاهر", "comfort": "راحت", "compact": "فشرده", "pause": "مکث", "resume": "ادامه", "clear": "پاک کردن", "live": "زنده", "reconnecting": "اتصال مجدد", "connection_issue": "مشکل اتصال", "translation_not_available": "ترجمه برای این زیرنویس در دسترس نیست؛ زبان اصلی نمایش داده می‌شود."
    },
}


def normalise_language(code: str | None) -> str:
    if not code:
        return SOURCE_LANGUAGE
    code = str(code).lower().split("-")[0].strip()
    return code if code in LANGUAGE_BY_CODE else SOURCE_LANGUAGE


def get_client_ui_strings() -> dict[str, dict[str, str]]:
    return CLIENT_UI_STRINGS


@dataclass(frozen=True)
class TranslationResult:
    text: str
    applied: bool
    warning: str | None = None


class LocalTranslator:
    """Optional local caption translation bridge.

    Caption translation is available when explicitly enabled by the operator. The live-caption core stays
    local and lightweight. If a church enables translation, the operator should
    also set a small maximum number of active translated languages because every
    additional language increases CPU/RAM use.

    Providers:
    - demo: prefixes text for testing routing; not a real translation.
    - argos: uses optional Argos Translate local models installed on the Mac.
    - disabled: no translation, source captions only.
    """

    def __init__(self, source_language: str = SOURCE_LANGUAGE):
        self.source_language = normalise_language(source_language)
        self._cache: dict[tuple[str, str, str], TranslationResult] = {}

    def provider_status(self, provider: str) -> dict:
        provider = (provider or "disabled").lower().strip()
        if provider in {"", "disabled", "none"}:
            return {"provider": "disabled", "ready": False, "message": "Translation provider is disabled."}
        if provider == "demo":
            return {"provider": "demo", "ready": True, "message": "Demo routing provider only; not real translation."}
        if provider == "argos":
            try:
                from argostranslate import package as argos_package  # type: ignore
                from argostranslate import translate as argos_translate  # type: ignore
                installed = argos_translate.get_installed_languages()
                pairs: list[str] = []
                for source in installed:
                    for target in installed:
                        if source.code != target.code:
                            translation = source.get_translation(target)
                            if translation is not None:
                                pairs.append(f"{source.code}->{target.code}")
                return {
                    "provider": "argos",
                    "ready": bool(pairs),
                    "message": f"Argos Translate installed. Installed pairs: {', '.join(sorted(set(pairs))) or 'none'}. Install models with scripts/install-translation-models-argos.sh.",
                }
            except Exception as exc:
                return {"provider": "argos", "ready": False, "message": f"Argos Translate is not installed or not ready: {exc}"}
        return {"provider": provider, "ready": False, "message": f"Unknown translation provider: {provider}"}

    def translate(self, text: str, target_language: str, *, enabled: bool, provider: str) -> TranslationResult:
        target_language = normalise_language(target_language)
        if target_language == self.source_language:
            return TranslationResult(text=text, applied=False)
        if not enabled:
            return TranslationResult(text=text, applied=False, warning="Translated captions are not currently enabled. Showing the source language.")
        provider = (provider or "disabled").lower().strip()
        if provider in {"", "disabled", "none"}:
            return TranslationResult(text=text, applied=False, warning="No local translation provider is configured.")

        cache_key = (provider, target_language, text)
        if cache_key in self._cache:
            return self._cache[cache_key]

        if provider == "demo":
            result = TranslationResult(
                text=f"[{target_language.upper()} demo] {text}",
                applied=True,
                warning="Demo provider only; not a real translation.",
            )
        elif provider == "argos":
            result = self._translate_with_argos(text, target_language)
        else:
            result = TranslationResult(text=text, applied=False, warning=f"Unknown translation provider: {provider}")

        if len(self._cache) > 2000:
            self._cache.clear()
        self._cache[cache_key] = result
        return result

    async def translate_async(self, text: str, target_language: str, *, enabled: bool, provider: str) -> TranslationResult:
        import asyncio
        return await asyncio.to_thread(self.translate, text, target_language, enabled=enabled, provider=provider)

    def _translate_with_argos(self, text: str, target_language: str) -> TranslationResult:
        try:
            from argostranslate import translate as argos_translate  # type: ignore
        except Exception as exc:
            return TranslationResult(text=text, applied=False, warning=f"Argos Translate is not installed: {exc}")

        try:
            translated = argos_translate.translate(text, self.source_language, target_language)
            if translated and translated.strip() and translated != text:
                return TranslationResult(text=translated, applied=True)

            # Some Argos installs may not have a direct pair. Because the source
            # language is normally English, direct en->target models are preferred.
            return TranslationResult(
                text=text,
                applied=False,
                warning=f"No installed Argos model for {self.source_language}->{target_language}.",
            )
        except Exception as exc:
            return TranslationResult(text=text, applied=False, warning=f"Argos Translate failed: {exc}")

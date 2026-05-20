from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Church Cap"
    app_version: str = "0.1.0"
    feedback_email: str = "info@churchcap.com"
    host: str = "0.0.0.0"
    port: int = 8080
    viewer_port: int = 8080
    operator_port: int = 9090
    dual_port_mode: bool = False
    lock_operator_to_localhost: bool = True
    public_base_url: str | None = None

    transcriber_mode: str = "faster_whisper"
    whisper_model: str = "base.en"
    whisper_device: str = "auto"
    whisper_compute_type: str = "auto"
    language: str = "en"

    audio_device: str | None = None
    sample_rate: int = 16000
    chunk_seconds: float = 2.0
    stream_window_seconds: float = 6.0
    stream_update_interval_seconds: float = 0.75
    stream_silence_finalise_seconds: float = 1.2
    stream_min_rms: float = 0.006
    stream_stability_passes: int = 2

    # Optional local translation scaffolding. Provider/language settings are prepared
    # by default, but the operator must explicitly enable translated captions in the web UI.
    translation_enabled: bool = False
    translation_provider: str = "argos"  # argos or demo; disabled is also accepted
    translation_allowed_languages: str = "en"
    translation_max_active_languages: int = 1

    church_name: str = "Church Cap"
    dnd_reminder: bool = True

    # Operator/admin security. If OPERATOR_PASSWORD is not set, the app
    # redirects to /setup on first use. Session secrets are rotated locally
    # on each application start in data/operator_auth.json.
    operator_password: str = "change-me"
    session_secret: str = "dev-only-change-this-secret"
    session_max_age_seconds: int = 60 * 60 * 8

    # Privacy defaults. These can also be changed on the operator page.
    transcript_retention_minutes: int = 120
    transcript_saving_enabled: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

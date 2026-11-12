use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

use serde::Serialize;
use tauri::{AppHandle, Emitter, State};
use tauri_plugin_updater::{Update, UpdaterExt};

use crate::lifecycle::EngineSupervisor;

const UPDATE_EVENT: &str = "church-cap://update-progress";
const UPDATER_PUBLIC_KEY_ID: &str = "25BF3CCF4B6CBB01";

#[derive(Clone)]
pub struct UpdateCoordinator {
    busy: Arc<AtomicBool>,
}

impl UpdateCoordinator {
    pub fn new() -> Self {
        Self {
            busy: Arc::new(AtomicBool::new(false)),
        }
    }

    fn begin(&self) -> Result<UpdateGuard, String> {
        self.busy
            .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
            .map_err(|_| "An update check or installation is already in progress.".to_string())?;
        Ok(UpdateGuard {
            busy: self.busy.clone(),
        })
    }
}

struct UpdateGuard {
    busy: Arc<AtomicBool>,
}

impl Drop for UpdateGuard {
    fn drop(&mut self) {
        self.busy.store(false, Ordering::Release);
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct UpdateResult {
    status: String,
    current_version: String,
    version: Option<String>,
    notes: Option<String>,
    published_at: Option<String>,
    detail: String,
}

impl UpdateResult {
    fn current(status: &str, detail: impl Into<String>) -> Self {
        Self {
            status: status.into(),
            current_version: env!("CARGO_PKG_VERSION").into(),
            version: None,
            notes: None,
            published_at: None,
            detail: detail.into(),
        }
    }

    fn available(update: &Update) -> Self {
        Self {
            status: "available".into(),
            current_version: update.current_version.clone(),
            version: Some(update.version.clone()),
            notes: update.body.clone(),
            published_at: update.date.map(|date| date.to_string()),
            detail: format!("Church Cap {} is ready to download.", update.version),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
struct UpdateProgress {
    phase: String,
    downloaded: u64,
    total: Option<u64>,
    detail: String,
}

fn emit_progress(
    app: &AppHandle,
    phase: &str,
    downloaded: u64,
    total: Option<u64>,
    detail: impl Into<String>,
) {
    let _ = app.emit(
        UPDATE_EVENT,
        UpdateProgress {
            phase: phase.into(),
            downloaded,
            total,
            detail: detail.into(),
        },
    );
}

#[derive(Debug)]
enum QueryError {
    Unpublished,
    Other(String),
}

async fn query_update(app: &AppHandle) -> Result<Option<Update>, QueryError> {
    let updater = app.updater().map_err(|error| {
        QueryError::Other(format!(
            "Church Cap could not initialise signed updates with trust root {UPDATER_PUBLIC_KEY_ID}: {error}"
        ))
    })?;
    updater.check().await.map_err(|error| match error {
        tauri_plugin_updater::Error::ReleaseNotFound => QueryError::Unpublished,
        error => QueryError::Other(format!(
            "Church Cap could not check its signed update channel: {error}"
        )),
    })
}

#[tauri::command]
pub async fn check_for_updates(
    app: AppHandle,
    coordinator: State<'_, UpdateCoordinator>,
) -> Result<UpdateResult, String> {
    let _guard = coordinator.begin()?;
    emit_progress(
        &app,
        "checking",
        0,
        None,
        "Checking for a signed Church Cap update…",
    );
    match query_update(&app).await {
        Ok(Some(update)) => {
            let result = UpdateResult::available(&update);
            emit_progress(&app, "available", 0, None, result.detail.clone());
            Ok(result)
        }
        Ok(None) => {
            let result = UpdateResult::current(
                "up_to_date",
                format!("Church Cap {} is up to date.", env!("CARGO_PKG_VERSION")),
            );
            emit_progress(&app, "up_to_date", 0, None, result.detail.clone());
            Ok(result)
        }
        Err(QueryError::Unpublished) => {
            let result = UpdateResult::current(
                "channel_unpublished",
                "The signed desktop update channel has not been published yet. Church Cap will keep using this installed version.",
            );
            emit_progress(&app, "channel_unpublished", 0, None, result.detail.clone());
            Ok(result)
        }
        Err(QueryError::Other(error)) => {
            emit_progress(&app, "error", 0, None, error.clone());
            Err(error)
        }
    }
}

#[tauri::command]
pub async fn install_update(
    app: AppHandle,
    coordinator: State<'_, UpdateCoordinator>,
    supervisor: State<'_, EngineSupervisor>,
) -> Result<UpdateResult, String> {
    let _guard = coordinator.begin()?;
    if supervisor.snapshot().captions_live {
        return Err(
            "Live captions are active. Stop captions before downloading and installing the update."
                .into(),
        );
    }

    emit_progress(&app, "checking", 0, None, "Confirming the signed update…");
    let update = match query_update(&app).await {
        Ok(Some(update)) => update,
        Ok(None) => {
            return Ok(UpdateResult::current(
                "up_to_date",
                format!(
                    "Church Cap {} is already up to date.",
                    env!("CARGO_PKG_VERSION")
                ),
            ));
        }
        Err(QueryError::Unpublished) => {
            return Ok(UpdateResult::current(
                "channel_unpublished",
                "The signed desktop update channel has not been published yet.",
            ));
        }
        Err(QueryError::Other(error)) => return Err(error),
    };

    let mut downloaded = 0_u64;
    let progress_app = app.clone();
    emit_progress(
        &app,
        "downloading",
        0,
        None,
        format!("Downloading Church Cap {}…", update.version),
    );
    let bytes = update
        .download(
            move |chunk_length, content_length| {
                downloaded = downloaded.saturating_add(chunk_length as u64);
                emit_progress(
                    &progress_app,
                    "downloading",
                    downloaded,
                    content_length,
                    "Downloading and verifying the signed update…",
                );
            },
            {
                let app = app.clone();
                move || emit_progress(&app, "verified", 0, None, "Update signature verified.")
            },
        )
        .await
        .map_err(|error| format!("Church Cap could not download or verify the update: {error}"))?;

    // Caption state may have changed while the package downloaded. The Rust
    // supervisor owns the final decision, even if the webview is stale.
    let restart_engine_on_failure = supervisor.begin_update_install(&app)?;
    emit_progress(
        &app,
        "installing",
        0,
        None,
        "Installing Church Cap and preparing to relaunch…",
    );
    if let Err(error) = update.install(bytes) {
        let detail = format!("Church Cap could not install the verified update: {error}");
        supervisor.recover_after_update_failure(&app, detail.clone(), restart_engine_on_failure);
        emit_progress(&app, "error", 0, None, detail.clone());
        return Err(detail);
    }

    emit_progress(
        &app,
        "installed",
        0,
        None,
        "Update installed. Relaunching Church Cap…",
    );
    app.restart();
}

#[cfg(test)]
mod tests {
    use super::UPDATER_PUBLIC_KEY_ID;

    #[test]
    fn updater_trust_root_identity_is_auditable() {
        assert_eq!(UPDATER_PUBLIC_KEY_ID, "25BF3CCF4B6CBB01");
    }

    #[test]
    fn the_plugin_missing_release_error_is_distinct_from_verification_errors() {
        let missing = tauri_plugin_updater::Error::ReleaseNotFound;
        assert!(matches!(
            missing,
            tauri_plugin_updater::Error::ReleaseNotFound
        ));
        assert!(!matches!(
            tauri_plugin_updater::Error::SignatureUtf8("invalid".into()),
            tauri_plugin_updater::Error::ReleaseNotFound
        ));
    }
}

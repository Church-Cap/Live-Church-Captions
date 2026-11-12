use std::fs;
use std::io::ErrorKind;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

const AUTH_DATA_DIRECTORY: &str = "data";
const AUTH_BACKUP_FILE: &str = "operator_auth.backup.json";
const AUTH_PRIMARY_FILE: &str = "operator_auth.json";
const RUNTIME_CONFIG_FILE: &str = "runtime_config.json";
const PASSWORD_RECOVERY_MARKER: &str = "operator_password_recovery.flag";
const FACTORY_RESET_MARKER: &str = "factory_reset.flag";
const FACTORY_RESET_STAGING: &str = ".factory-reset-staging";
// Written into the canonical data directory once the legacy Tauri-derived
// root has been moved in, so the move never repeats or resurrects old state.
const LEGACY_MIGRATION_MARKER: &str = "legacy_data_migration.json";
const LEGACY_MIGRATION_NOTE: &str = "MOVED-TO-CHURCH-CAP.txt";
const PRE_MIGRATION_SUFFIX: &str = ".pre-migration";
// The same bounded list factory reset owns. v0.8.0 desktop wrappers kept all
// of these beneath Tauri's identifier-derived directory, which v0.9.0 no
// longer uses, so a normal update must carry them across once.
const FACTORY_RESET_DIRECTORIES: [&str; 10] = [
    "data",
    "config",
    "cache",
    "logs",
    "updates",
    "recovery",
    "exports",
    "models",
    "tts",
    "cuda-runtime",
];

fn operator_auth_paths(app_data_dir: &Path) -> [PathBuf; 2] {
    let auth_data_dir = app_data_dir.join(AUTH_DATA_DIRECTORY);
    [
        auth_data_dir.join(AUTH_BACKUP_FILE),
        auth_data_dir.join(AUTH_PRIMARY_FILE),
    ]
}

pub fn reset_operator_auth(app_data_dir: &Path) -> Result<usize, String> {
    let mut existing = Vec::new();
    // Inspect everything before writing the recovery marker or changing auth.
    for path in operator_auth_paths(app_data_dir) {
        match fs::symlink_metadata(&path) {
            Ok(metadata) if metadata.file_type().is_file() || metadata.file_type().is_symlink() => {
                existing.push(path);
            }
            Ok(_) => {
                return Err(
                    "Church Cap found an unexpected item in its authentication storage and left it unchanged."
                        .into(),
                );
            }
            Err(error) if error.kind() == ErrorKind::NotFound => {}
            Err(error) => {
                return Err(format!(
                    "Church Cap could not inspect its stored operator authentication: {error}"
                ));
            }
        }
    }
    if existing.is_empty() {
        return Ok(0);
    }

    let marker = app_data_dir
        .join(AUTH_DATA_DIRECTORY)
        .join(PASSWORD_RECOVERY_MARKER);
    fs::write(&marker, b"password-reset\n").map_err(|error| {
        format!(
            "Church Cap could not prepare password recovery, so the existing password was left unchanged: {error}"
        )
    })?;

    // The array order keeps the primary password intact when backup removal
    // fails. If a later removal fails, retain the marker for safe recovery.
    let mut removed = 0;
    for path in existing {
        fs::remove_file(&path).map_err(|error| {
            format!("Church Cap could not remove its stored operator authentication: {error}")
        })?;
        removed += 1;
    }
    Ok(removed)
}

fn restore_staged_items(moved: &[(PathBuf, PathBuf)]) {
    for (original, staged) in moved.iter().rev() {
        if fs::symlink_metadata(staged).is_ok() {
            let _ = fs::create_dir_all(original.parent().unwrap_or_else(|| Path::new(".")));
            let _ = fs::rename(staged, original);
        }
    }
}

pub fn factory_reset_app_data(app_data_dir: &Path) -> Result<usize, String> {
    fs::create_dir_all(app_data_dir).map_err(|error| {
        format!("Church Cap could not prepare its application-data folder: {error}")
    })?;
    let staging = app_data_dir.join(FACTORY_RESET_STAGING);
    match fs::symlink_metadata(&staging) {
        Ok(_) => {
            return Err(
                "A previous Church Cap factory-reset staging folder still exists. Leave it in place and seek support before trying again."
                    .into(),
            )
        }
        Err(error) if error.kind() == ErrorKind::NotFound => {}
        Err(error) => {
            return Err(format!(
                "Church Cap could not inspect its factory-reset staging folder: {error}"
            ))
        }
    }
    fs::create_dir(&staging)
        .map_err(|error| format!("Church Cap could not prepare factory reset: {error}"))?;

    let mut moved: Vec<(PathBuf, PathBuf)> = Vec::new();
    for (index, name) in FACTORY_RESET_DIRECTORIES.iter().enumerate() {
        let original = app_data_dir.join(name);
        match fs::symlink_metadata(&original) {
            Ok(_) => {
                let staged = staging.join(format!("item-{index}"));
                if let Err(error) = fs::rename(&original, &staged) {
                    restore_staged_items(&moved);
                    let _ = fs::remove_dir(&staging);
                    return Err(format!(
                        "Church Cap could not stage {name} for factory reset, so existing data was restored: {error}"
                    ));
                }
                moved.push((original, staged));
            }
            Err(error) if error.kind() == ErrorKind::NotFound => {}
            Err(error) => {
                restore_staged_items(&moved);
                let _ = fs::remove_dir(&staging);
                return Err(format!(
                    "Church Cap could not inspect {name}, so factory reset was cancelled: {error}"
                ));
            }
        }
    }

    let data_dir = app_data_dir.join(AUTH_DATA_DIRECTORY);
    let marker = data_dir.join(FACTORY_RESET_MARKER);
    if let Err(error) =
        fs::create_dir_all(&data_dir).and_then(|_| fs::write(&marker, b"factory-reset\n"))
    {
        let _ = fs::remove_dir_all(&data_dir);
        restore_staged_items(&moved);
        let _ = fs::remove_dir(&staging);
        return Err(format!(
            "Church Cap could not activate first-time setup, so existing data was restored: {error}"
        ));
    }

    // Reset is active once the marker exists. Cleanup is best-effort: a failed
    // staging removal must not reintroduce old configuration or credentials.
    let _ = fs::remove_dir_all(&staging);
    Ok(moved.len())
}

/// Remove the known Church Cap directories from a legacy data root that is no
/// longer used for engine start. Factory reset calls this so an old password
/// file and downloaded models do not survive a reset in the abandoned root.
pub fn clear_legacy_app_data(legacy_root: &Path, canonical_root: &Path) -> Result<usize, String> {
    if same_root(legacy_root, canonical_root) || !legacy_root.is_dir() {
        return Ok(0);
    }
    let mut removed = 0;
    for name in FACTORY_RESET_DIRECTORIES {
        let path = legacy_root.join(name);
        match fs::symlink_metadata(&path) {
            Ok(_) => {
                fs::remove_dir_all(&path).map_err(|error| {
                    format!(
                        "Church Cap could not remove {name} from its previous data folder: {error}"
                    )
                })?;
                removed += 1;
            }
            Err(error) if error.kind() == ErrorKind::NotFound => {}
            Err(error) => {
                return Err(format!(
                    "Church Cap could not inspect {name} in its previous data folder: {error}"
                ));
            }
        }
    }
    Ok(removed)
}

#[derive(Debug, Default, PartialEq, Eq)]
pub struct LegacyMigrationSummary {
    /// Top-level directories or merged children moved into the canonical root.
    pub moved: usize,
    /// Children left behind because the canonical root already had them.
    pub left_in_place: usize,
}

fn same_root(left: &Path, right: &Path) -> bool {
    match (fs::canonicalize(left), fs::canonicalize(right)) {
        (Ok(left), Ok(right)) => left == right,
        _ => left == right,
    }
}

fn is_cross_device(error: &std::io::Error) -> bool {
    #[cfg(windows)]
    const CROSS_DEVICE: i32 = 17; // ERROR_NOT_SAME_DEVICE
    #[cfg(not(windows))]
    const CROSS_DEVICE: i32 = 18; // EXDEV
    error.raw_os_error() == Some(CROSS_DEVICE)
}

fn copy_tree(source: &Path, destination: &Path) -> std::io::Result<()> {
    let metadata = fs::symlink_metadata(source)?;
    if metadata.file_type().is_symlink() {
        // A symlink inside application data is unexpected; do not follow it
        // into arbitrary locations, and do not silently drop the move either.
        return Err(std::io::Error::other(format!(
            "{} is a symbolic link",
            source.display()
        )));
    }
    if metadata.is_dir() {
        fs::create_dir_all(destination)?;
        for entry in fs::read_dir(source)? {
            let entry = entry?;
            copy_tree(&entry.path(), &destination.join(entry.file_name()))?;
        }
        Ok(())
    } else {
        fs::copy(source, destination).map(|_| ())
    }
}

/// One reversible step of a migration. `moved` entries are renamed back on
/// rollback; `copied` entries are removed on rollback because their source
/// still exists.
enum MigrationStep {
    Moved { from: PathBuf, to: PathBuf },
    Copied { to: PathBuf },
}

fn relocate(
    source: &Path,
    destination: &Path,
    steps: &mut Vec<MigrationStep>,
) -> Result<(), String> {
    match fs::rename(source, destination) {
        Ok(()) => {
            steps.push(MigrationStep::Moved {
                from: source.to_path_buf(),
                to: destination.to_path_buf(),
            });
            Ok(())
        }
        Err(error) if is_cross_device(&error) => {
            copy_tree(source, destination).map_err(|error| {
                let _ = fs::remove_dir_all(destination);
                let _ = fs::remove_file(destination);
                format!(
                    "Church Cap could not copy {} into its data folder: {error}",
                    source.display()
                )
            })?;
            steps.push(MigrationStep::Copied {
                to: destination.to_path_buf(),
            });
            Ok(())
        }
        Err(error) => Err(format!(
            "Church Cap could not move {} into its data folder: {error}",
            source.display()
        )),
    }
}

fn rollback_migration(steps: &[MigrationStep]) {
    for step in steps.iter().rev() {
        match step {
            MigrationStep::Moved { from, to } => {
                let _ = fs::create_dir_all(from.parent().unwrap_or_else(|| Path::new(".")));
                let _ = fs::rename(to, from);
            }
            MigrationStep::Copied { to } => {
                let _ = fs::remove_dir_all(to);
                let _ = fs::remove_file(to);
            }
        }
    }
}

fn legacy_root_holds_installation(legacy_root: &Path) -> bool {
    let data = legacy_root.join(AUTH_DATA_DIRECTORY);
    data.join(AUTH_PRIMARY_FILE).is_file() || data.join(RUNTIME_CONFIG_FILE).is_file()
}

/// Whether the wrapper should carry a previous installation's data across.
///
/// The canonical root wins whenever it already holds an operator password,
/// a pending factory reset or a completed migration; the legacy root must
/// actually contain an installation for there to be anything to carry.
pub fn legacy_root_needs_migration(legacy_root: &Path, canonical_root: &Path) -> bool {
    if same_root(legacy_root, canonical_root) {
        return false;
    }
    let canonical_data = canonical_root.join(AUTH_DATA_DIRECTORY);
    if canonical_data.join(AUTH_PRIMARY_FILE).is_file()
        || canonical_data.join(FACTORY_RESET_MARKER).is_file()
        || canonical_data.join(LEGACY_MIGRATION_MARKER).is_file()
    {
        return false;
    }
    legacy_root_holds_installation(legacy_root)
}

/// Move a v0.8.0-era desktop data root into the canonical Church Cap root.
///
/// Known top-level directories are renamed whole when the canonical root does
/// not have them. Where it does, the children are merged one level deep: a
/// colliding file inside `data/` is set aside with a `.pre-migration` suffix
/// rather than overwritten, and colliding entries elsewhere (models, caches)
/// stay in the legacy root. Any failure rolls every step back and returns an
/// error, so the engine never starts onboarding over a half-moved installation.
pub fn migrate_legacy_app_data(
    legacy_root: &Path,
    canonical_root: &Path,
) -> Result<Option<LegacyMigrationSummary>, String> {
    if !legacy_root_needs_migration(legacy_root, canonical_root) {
        return Ok(None);
    }
    fs::create_dir_all(canonical_root).map_err(|error| {
        format!("Church Cap could not prepare its application-data folder: {error}")
    })?;

    let mut steps: Vec<MigrationStep> = Vec::new();
    let mut summary = LegacyMigrationSummary::default();
    let outcome = (|| -> Result<(), String> {
        for name in FACTORY_RESET_DIRECTORIES {
            let source = legacy_root.join(name);
            match fs::symlink_metadata(&source) {
                Ok(metadata) if metadata.is_dir() => {}
                Ok(_) => continue,
                Err(error) if error.kind() == ErrorKind::NotFound => continue,
                Err(error) => {
                    return Err(format!(
                        "Church Cap could not inspect {name} in its previous data folder: {error}"
                    ));
                }
            }
            let destination = canonical_root.join(name);
            if !destination.exists() {
                relocate(&source, &destination, &mut steps)?;
                summary.moved += 1;
                continue;
            }
            let entries = fs::read_dir(&source).map_err(|error| {
                format!("Church Cap could not read {name} in its previous data folder: {error}")
            })?;
            for entry in entries {
                let entry = entry.map_err(|error| {
                    format!("Church Cap could not read {name} in its previous data folder: {error}")
                })?;
                let child_source = entry.path();
                let child_destination = destination.join(entry.file_name());
                if child_destination.exists() {
                    if name != AUTH_DATA_DIRECTORY {
                        summary.left_in_place += 1;
                        continue;
                    }
                    let mut set_aside = child_destination.as_os_str().to_owned();
                    set_aside.push(PRE_MIGRATION_SUFFIX);
                    relocate(&child_destination, Path::new(&set_aside), &mut steps)?;
                }
                relocate(&child_source, &child_destination, &mut steps)?;
                summary.moved += 1;
            }
        }
        let canonical_data = canonical_root.join(AUTH_DATA_DIRECTORY);
        fs::create_dir_all(&canonical_data)
            .map_err(|error| format!("Church Cap could not record its data migration: {error}"))?;
        let migrated_at = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|elapsed| elapsed.as_secs())
            .unwrap_or_default();
        let record = format!(
            "{{\n  \"source\": {},\n  \"migrated_at_unix\": {migrated_at},\n  \"moved\": {},\n  \"left_in_place\": {}\n}}\n",
            serde_json::to_string(&legacy_root.display().to_string())
                .unwrap_or_else(|_| "\"\"".into()),
            summary.moved,
            summary.left_in_place
        );
        fs::write(canonical_data.join(LEGACY_MIGRATION_MARKER), record)
            .map_err(|error| format!("Church Cap could not record its data migration: {error}"))
    })();

    if let Err(error) = outcome {
        rollback_migration(&steps);
        return Err(format!(
            "{error} Church Cap restored its previous data folder and did not start, so no settings were lost."
        ));
    }
    // The note is a courtesy for anyone who finds the old folder; it is not
    // part of the migration's correctness.
    let _ = fs::write(
        legacy_root.join(LEGACY_MIGRATION_NOTE),
        format!(
            "Church Cap moved this folder's settings and downloads to:\n{}\n",
            canonical_root.display()
        ),
    );
    Ok(Some(summary))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temporary_data_dir(test_name: &str) -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock should follow the Unix epoch")
            .as_nanos();
        std::env::temp_dir().join(format!(
            "church-cap-{test_name}-{}-{nonce}",
            std::process::id()
        ))
    }

    #[test]
    fn reset_removes_only_the_known_primary_and_backup_files() {
        let root = temporary_data_dir("password-reset");
        let data = root.join(AUTH_DATA_DIRECTORY);
        fs::create_dir_all(&data).unwrap();
        let [backup, primary] = operator_auth_paths(&root);
        fs::write(&backup, "backup").unwrap();
        fs::write(&primary, "primary").unwrap();
        let unrelated = data.join("runtime.json");
        fs::write(&unrelated, "keep").unwrap();

        assert_eq!(reset_operator_auth(&root).unwrap(), 2);
        assert!(!backup.exists());
        assert!(!primary.exists());
        assert_eq!(fs::read_to_string(&unrelated).unwrap(), "keep");
        assert_eq!(
            fs::read_to_string(data.join(PASSWORD_RECOVERY_MARKER)).unwrap(),
            "password-reset\n"
        );

        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn reset_is_idempotent_when_no_password_has_been_stored() {
        let root = temporary_data_dir("empty-password-reset");
        assert_eq!(reset_operator_auth(&root).unwrap(), 0);
        assert!(
            !root
                .join(AUTH_DATA_DIRECTORY)
                .join(PASSWORD_RECOVERY_MARKER)
                .exists()
        );
    }

    #[test]
    fn factory_reset_removes_only_known_state_and_opens_full_setup() {
        let root = temporary_data_dir("factory-reset");
        for directory in FACTORY_RESET_DIRECTORIES {
            let path = root.join(directory);
            fs::create_dir_all(&path).unwrap();
            fs::write(path.join("retained-before-reset.txt"), directory).unwrap();
        }
        let unrelated = root.join("keep-me.txt");
        fs::write(&unrelated, "keep").unwrap();

        assert_eq!(
            factory_reset_app_data(&root).unwrap(),
            FACTORY_RESET_DIRECTORIES.len()
        );
        for directory in FACTORY_RESET_DIRECTORIES {
            if directory != AUTH_DATA_DIRECTORY {
                assert!(!root.join(directory).exists());
            }
        }
        assert_eq!(fs::read_to_string(&unrelated).unwrap(), "keep");
        assert_eq!(
            fs::read_to_string(root.join(AUTH_DATA_DIRECTORY).join(FACTORY_RESET_MARKER)).unwrap(),
            "factory-reset\n"
        );
        assert!(!root.join(FACTORY_RESET_STAGING).exists());

        fs::remove_dir_all(root).unwrap();
    }

    /// Lay down what a v0.8.0 desktop wrapper left in Tauri's identifier
    /// directory: a password, settings, a downloaded model and a voice pack.
    fn seed_legacy_installation(legacy: &Path) {
        let data = legacy.join(AUTH_DATA_DIRECTORY);
        fs::create_dir_all(&data).unwrap();
        fs::write(data.join(AUTH_PRIMARY_FILE), "legacy-password").unwrap();
        fs::write(
            data.join(RUNTIME_CONFIG_FILE),
            "{\"translation_allowed_languages\": [\"en\", \"fr\"]}",
        )
        .unwrap();
        let model = legacy.join("models").join("small100-ct2-int8");
        fs::create_dir_all(&model).unwrap();
        fs::write(model.join("model.bin"), "weights").unwrap();
        let voices = legacy.join("tts");
        fs::create_dir_all(&voices).unwrap();
        fs::write(voices.join("voices.json"), "[]").unwrap();
    }

    #[test]
    fn upgrade_from_legacy_root_moves_the_installation_once() {
        let root = temporary_data_dir("legacy-migration");
        let legacy = root.join("org.churchcap.desktop");
        let canonical = root.join("Church Cap");
        seed_legacy_installation(&legacy);

        assert!(legacy_root_needs_migration(&legacy, &canonical));
        let summary = migrate_legacy_app_data(&legacy, &canonical)
            .unwrap()
            .unwrap();
        assert_eq!(
            summary,
            LegacyMigrationSummary {
                moved: 3,
                left_in_place: 0
            }
        );

        let data = canonical.join(AUTH_DATA_DIRECTORY);
        assert_eq!(
            fs::read_to_string(data.join(AUTH_PRIMARY_FILE)).unwrap(),
            "legacy-password"
        );
        assert!(
            fs::read_to_string(data.join(RUNTIME_CONFIG_FILE))
                .unwrap()
                .contains("\"fr\"")
        );
        assert_eq!(
            fs::read_to_string(canonical.join("models/small100-ct2-int8/model.bin")).unwrap(),
            "weights"
        );
        assert!(canonical.join("tts/voices.json").is_file());
        let record = fs::read_to_string(data.join(LEGACY_MIGRATION_MARKER)).unwrap();
        assert!(record.contains("org.churchcap.desktop"));
        assert!(legacy.join(LEGACY_MIGRATION_NOTE).is_file());
        assert!(!legacy.join(AUTH_DATA_DIRECTORY).exists());

        // A second start must not repeat or resurrect anything.
        assert!(!legacy_root_needs_migration(&legacy, &canonical));
        assert_eq!(migrate_legacy_app_data(&legacy, &canonical).unwrap(), None);

        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn migration_never_replaces_an_installation_already_in_the_canonical_root() {
        let root = temporary_data_dir("legacy-migration-guard");
        let legacy = root.join("org.churchcap.desktop");
        let canonical = root.join("Church Cap");
        seed_legacy_installation(&legacy);
        let canonical_data = canonical.join(AUTH_DATA_DIRECTORY);
        fs::create_dir_all(&canonical_data).unwrap();
        fs::write(canonical_data.join(AUTH_PRIMARY_FILE), "current-password").unwrap();

        assert!(!legacy_root_needs_migration(&legacy, &canonical));
        assert_eq!(migrate_legacy_app_data(&legacy, &canonical).unwrap(), None);
        assert_eq!(
            fs::read_to_string(canonical_data.join(AUTH_PRIMARY_FILE)).unwrap(),
            "current-password"
        );
        assert!(
            legacy
                .join(AUTH_DATA_DIRECTORY)
                .join(AUTH_PRIMARY_FILE)
                .is_file()
        );

        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn migration_waits_while_a_factory_reset_is_in_progress() {
        let root = temporary_data_dir("legacy-migration-reset");
        let legacy = root.join("org.churchcap.desktop");
        let canonical = root.join("Church Cap");
        seed_legacy_installation(&legacy);
        let canonical_data = canonical.join(AUTH_DATA_DIRECTORY);
        fs::create_dir_all(&canonical_data).unwrap();
        fs::write(canonical_data.join(FACTORY_RESET_MARKER), "factory-reset\n").unwrap();

        assert!(!legacy_root_needs_migration(&legacy, &canonical));
        assert_eq!(migrate_legacy_app_data(&legacy, &canonical).unwrap(), None);
        assert!(!canonical_data.join(AUTH_PRIMARY_FILE).exists());

        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn migration_merges_into_existing_directories_without_overwriting() {
        let root = temporary_data_dir("legacy-migration-merge");
        let legacy = root.join("org.churchcap.desktop");
        let canonical = root.join("Church Cap");
        seed_legacy_installation(&legacy);
        // A source-tree run already created a partial canonical root: a
        // settings file without a password, and the same model name.
        let canonical_data = canonical.join(AUTH_DATA_DIRECTORY);
        fs::create_dir_all(&canonical_data).unwrap();
        fs::write(
            canonical_data.join(RUNTIME_CONFIG_FILE),
            "{\"source\": true}",
        )
        .unwrap();
        let canonical_model = canonical.join("models").join("small100-ct2-int8");
        fs::create_dir_all(&canonical_model).unwrap();
        fs::write(canonical_model.join("model.bin"), "already-here").unwrap();

        let summary = migrate_legacy_app_data(&legacy, &canonical)
            .unwrap()
            .unwrap();
        // data: password + settings moved (2); tts moved whole (1); model left.
        assert_eq!(
            summary,
            LegacyMigrationSummary {
                moved: 3,
                left_in_place: 1
            }
        );
        assert_eq!(
            fs::read_to_string(canonical_data.join(AUTH_PRIMARY_FILE)).unwrap(),
            "legacy-password"
        );
        assert!(
            fs::read_to_string(canonical_data.join(RUNTIME_CONFIG_FILE))
                .unwrap()
                .contains("\"fr\"")
        );
        assert_eq!(
            fs::read_to_string(
                canonical_data.join(format!("{RUNTIME_CONFIG_FILE}{PRE_MIGRATION_SUFFIX}"))
            )
            .unwrap(),
            "{\"source\": true}"
        );
        assert_eq!(
            fs::read_to_string(canonical_model.join("model.bin")).unwrap(),
            "already-here"
        );
        assert!(legacy.join("models/small100-ct2-int8/model.bin").is_file());

        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn migration_ignores_an_empty_or_identical_legacy_root() {
        let root = temporary_data_dir("legacy-migration-empty");
        let legacy = root.join("org.churchcap.desktop");
        let canonical = root.join("Church Cap");
        fs::create_dir_all(legacy.join("logs")).unwrap();
        assert!(!legacy_root_needs_migration(&legacy, &canonical));
        assert_eq!(migrate_legacy_app_data(&legacy, &canonical).unwrap(), None);
        assert!(!canonical.exists());

        seed_legacy_installation(&canonical);
        assert!(!legacy_root_needs_migration(&canonical, &canonical));

        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn migration_rolls_back_when_a_step_fails() {
        let root = temporary_data_dir("legacy-migration-rollback");
        let legacy = root.join("org.churchcap.desktop");
        let canonical = root.join("Church Cap");
        seed_legacy_installation(&legacy);
        // The canonical tts entry is a file, so merging the legacy tts
        // directory's children into it must fail after data/ already moved.
        fs::create_dir_all(&canonical).unwrap();
        fs::write(canonical.join("tts"), "not-a-directory").unwrap();

        let error = migrate_legacy_app_data(&legacy, &canonical).unwrap_err();
        assert!(
            error.contains("restored its previous data folder"),
            "{error}"
        );
        assert_eq!(
            fs::read_to_string(legacy.join(AUTH_DATA_DIRECTORY).join(AUTH_PRIMARY_FILE)).unwrap(),
            "legacy-password"
        );
        assert!(legacy.join("models/small100-ct2-int8/model.bin").is_file());
        assert!(
            !canonical
                .join(AUTH_DATA_DIRECTORY)
                .join(AUTH_PRIMARY_FILE)
                .exists()
        );
        assert!(!canonical.join("models").exists());
        assert!(
            !canonical
                .join(AUTH_DATA_DIRECTORY)
                .join(LEGACY_MIGRATION_MARKER)
                .exists()
        );
        assert!(!legacy.join(LEGACY_MIGRATION_NOTE).exists());

        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn factory_reset_can_clear_the_abandoned_legacy_root() {
        let root = temporary_data_dir("legacy-clear");
        let legacy = root.join("org.churchcap.desktop");
        let canonical = root.join("Church Cap");
        seed_legacy_installation(&legacy);
        fs::write(legacy.join("keep-me.txt"), "keep").unwrap();

        assert_eq!(clear_legacy_app_data(&legacy, &canonical).unwrap(), 3);
        assert!(!legacy.join(AUTH_DATA_DIRECTORY).exists());
        assert!(!legacy.join("models").exists());
        assert!(!legacy.join("tts").exists());
        assert_eq!(
            fs::read_to_string(legacy.join("keep-me.txt")).unwrap(),
            "keep"
        );
        assert_eq!(clear_legacy_app_data(&legacy, &legacy).unwrap(), 0);
        assert_eq!(
            clear_legacy_app_data(&root.join("missing"), &canonical).unwrap(),
            0
        );

        fs::remove_dir_all(root).unwrap();
    }
}

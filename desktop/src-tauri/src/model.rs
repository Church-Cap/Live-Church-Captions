use serde::{Deserialize, Serialize};

pub const ENGINE_PROTOCOL_VERSION: u16 = 2;
pub const ENGINE_EVENT_PREFIX: &str = "CHURCH_CAP_ENGINE_EVENT=";
pub const ENGINE_REQUEST_PREFIX: &str = "CHURCH_CAP_ENGINE_REQUEST=";
pub const ENGINE_COMMAND_PREFIX: &str = "CHURCH_CAP_ENGINE_COMMAND=";

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SupervisorPhase {
    Stopped,
    Starting,
    Ready,
    CaptionsLive,
    Stopping,
    Updating,
    RecoveryRequired,
    Error,
}

impl SupervisorPhase {
    pub fn engine_is_running(self) -> bool {
        matches!(
            self,
            Self::Starting | Self::Ready | Self::CaptionsLive | Self::Stopping
        )
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SupervisorSnapshot {
    pub phase: SupervisorPhase,
    pub detail: String,
    pub supervisor_version: String,
    pub engine_version: Option<String>,
    pub engine_protocol_version: u16,
    pub viewer_url: String,
    pub operator_url: String,
    pub pid: Option<u32>,
    pub captions_live: bool,
    pub health_confirmed: bool,
    pub restart_attempts: u8,
}

impl Default for SupervisorSnapshot {
    fn default() -> Self {
        Self {
            phase: SupervisorPhase::Stopped,
            detail: "Church Cap is not running.".into(),
            supervisor_version: env!("CARGO_PKG_VERSION").into(),
            engine_version: None,
            engine_protocol_version: ENGINE_PROTOCOL_VERSION,
            viewer_url: "http://127.0.0.1:8080/".into(),
            operator_url: "http://127.0.0.1:9090/operator".into(),
            pid: None,
            captions_live: false,
            health_confirmed: false,
            restart_attempts: 0,
        }
    }
}

#[derive(Debug, Deserialize)]
pub struct EngineEvent {
    pub state: String,
    pub app_version: String,
    pub protocol_version: u16,
    pub viewer_url: String,
    pub operator_url: String,
    pub detail: String,
    pub pid: u32,
}

impl EngineEvent {
    pub fn parse(line: &str) -> Option<Self> {
        serde_json::from_str(line.strip_prefix(ENGINE_EVENT_PREFIX)?).ok()
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EngineRequest {
    pub request: String,
    pub protocol_version: u16,
    pub pid: u32,
}

impl EngineRequest {
    pub fn parse(line: &str) -> Option<Self> {
        serde_json::from_str(line.strip_prefix(ENGINE_REQUEST_PREFIX)?).ok()
    }
}

#[derive(Debug, Serialize)]
pub struct EngineCommand<'a> {
    pub command: &'a str,
    pub protocol_version: u16,
}

impl EngineCommand<'_> {
    pub fn shutdown_line() -> String {
        let payload = Self {
            command: "shutdown",
            protocol_version: ENGINE_PROTOCOL_VERSION,
        };
        format!(
            "{ENGINE_COMMAND_PREFIX}{}\n",
            serde_json::to_string(&payload).expect("static engine command must serialize")
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_versioned_engine_events() {
        let event = EngineEvent::parse(
            "CHURCH_CAP_ENGINE_EVENT={\"state\":\"ready\",\"app_version\":\"0.9.0\",\"protocol_version\":2,\"viewer_url\":\"http://127.0.0.1:8080/\",\"operator_url\":\"http://127.0.0.1:9090/operator\",\"detail\":\"\",\"pid\":42}",
        )
        .expect("event should parse");
        assert_eq!(event.protocol_version, ENGINE_PROTOCOL_VERSION);
        assert_eq!(event.pid, 42);
    }

    #[test]
    fn parses_only_well_formed_engine_requests() {
        let line = "CHURCH_CAP_ENGINE_REQUEST={\"request\":\"open_updates\",\"protocol_version\":2,\"pid\":42}";
        let request = EngineRequest::parse(line).expect("request should parse");
        assert_eq!(request.request, "open_updates");
        assert_eq!(request.protocol_version, ENGINE_PROTOCOL_VERSION);
        assert_eq!(request.pid, 42);
        assert!(EngineRequest::parse("CHURCH_CAP_ENGINE_EVENT={}").is_none());
        assert!(EngineRequest::parse("CHURCH_CAP_ENGINE_REQUEST=not-json").is_none());
        assert!(EngineRequest::parse("CHURCH_CAP_ENGINE_REQUEST={\"request\":\"open_updates\",\"protocol_version\":2,\"pid\":42,\"extra\":true}").is_none());
        assert!(EngineRequest::parse("CHURCH_CAP_ENGINE_REQUEST={\"request\":\"open_updates\",\"protocol_version\":2,\"pid\":\"42\"}").is_none());
    }

    #[test]
    fn shutdown_command_contains_no_arbitrary_arguments() {
        assert_eq!(
            EngineCommand::shutdown_line(),
            "CHURCH_CAP_ENGINE_COMMAND={\"command\":\"shutdown\",\"protocol_version\":2}\n"
        );
    }

    #[test]
    fn parses_caption_lifecycle_events() {
        for state in ["captions_live", "captions_idle"] {
            let line = format!(
                "CHURCH_CAP_ENGINE_EVENT={{\"state\":\"{state}\",\"app_version\":\"0.9.0\",\"protocol_version\":2,\"viewer_url\":\"http://127.0.0.1:8080/\",\"operator_url\":\"http://127.0.0.1:9090/operator\",\"detail\":\"caption transition\",\"pid\":42}}"
            );
            assert_eq!(EngineEvent::parse(&line).unwrap().state, state);
        }
    }
}

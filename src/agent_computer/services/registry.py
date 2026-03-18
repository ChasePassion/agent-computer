from __future__ import annotations

import threading
from dataclasses import dataclass, field

from agent_computer.runtime import DEFAULT_CODEX_TARGET_CWD
from agent_computer.services.action_service import ActionService
from agent_computer.services.browser_assist_connection_manager import BrowserAssistConnectionManager
from agent_computer.services.browser_assist_service import BrowserAssistService
from agent_computer.services.capture_service import CaptureService
from agent_computer.services.codex_session_watcher import CodexSessionWatcher
from agent_computer.services.live_output_service import LiveOutputService
from agent_computer.services.navigation_service import NavigationService
from agent_computer.services.observation_service import ObservationService
from agent_computer.services.session_service import SessionService


@dataclass
class ServiceRegistry:
    session: SessionService
    capture: CaptureService
    actions: ActionService
    navigation: NavigationService
    observation: ObservationService
    live_output: LiveOutputService
    codex_session_watcher: CodexSessionWatcher
    browser_assist_connections: BrowserAssistConnectionManager
    browser_assist: BrowserAssistService
    execution_lock: threading.RLock = field(default_factory=threading.RLock)


def create_service_registry(*, host: str, port: int) -> ServiceRegistry:
    session = SessionService()
    execution_lock = threading.RLock()
    capture = CaptureService(session)
    actions = ActionService()
    navigation = NavigationService(session)
    observation = ObservationService(session, host=host, port=port)
    live_output = LiveOutputService()
    codex_session_watcher = CodexSessionWatcher(live_output, target_cwd=DEFAULT_CODEX_TARGET_CWD)
    browser_assist_connections = BrowserAssistConnectionManager(session)
    browser_assist = BrowserAssistService(session, browser_assist_connections)
    return ServiceRegistry(
        session=session,
        capture=capture,
        actions=actions,
        navigation=navigation,
        observation=observation,
        live_output=live_output,
        codex_session_watcher=codex_session_watcher,
        browser_assist_connections=browser_assist_connections,
        browser_assist=browser_assist,
        execution_lock=execution_lock,
    )

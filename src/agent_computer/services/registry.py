from __future__ import annotations

import threading
from dataclasses import dataclass, field

from agent_computer.display import validate_window_preconditions
from agent_computer.runtime import DEFAULT_CODEX_TARGET_CWD
from agent_computer.services.action_service import ActionService
from agent_computer.services.action_coordinator import ActionCoordinator
from agent_computer.services.browser_assist_connection_manager import BrowserAssistConnectionManager
from agent_computer.services.browser_assist_service import BrowserAssistService
from agent_computer.services.capture_service import CaptureService
from agent_computer.services.codex_session_watcher import CodexSessionWatcher
from agent_computer.services.live_output_service import LiveOutputService
from agent_computer.services.metrics_service import MetricsService
from agent_computer.services.navigation_service import NavigationService
from agent_computer.services.observation_service import ObservationService
from agent_computer.services.session_service import SessionService
from agent_computer.uia import UIAClient


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
    action_coordinator: ActionCoordinator
    metrics: MetricsService
    uia: UIAClient
    execution_lock: threading.RLock = field(default_factory=threading.RLock)


def create_service_registry(*, host: str, port: int) -> ServiceRegistry:
    session = SessionService()
    metrics = MetricsService()
    execution_lock = threading.RLock()
    capture = CaptureService(session)
    actions = ActionService()
    navigation = NavigationService(session)
    observation = ObservationService(session, host=host, port=port, metrics=metrics)
    live_output = LiveOutputService()
    codex_session_watcher = CodexSessionWatcher(live_output, target_cwd=DEFAULT_CODEX_TARGET_CWD)
    browser_assist_connections = BrowserAssistConnectionManager(session, metrics=metrics)
    browser_assist = BrowserAssistService(session, browser_assist_connections)
    uia = UIAClient()
    action_coordinator = ActionCoordinator(
        actions,
        observation,
        execution_lock=execution_lock,
        metrics=metrics,
        display_precondition_validator=validate_window_preconditions,
    )
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
        action_coordinator=action_coordinator,
        metrics=metrics,
        uia=uia,
        execution_lock=execution_lock,
    )

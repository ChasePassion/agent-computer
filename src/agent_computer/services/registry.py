from __future__ import annotations

import threading
from dataclasses import dataclass, field

from agent_computer.services.action_service import ActionService
from agent_computer.services.capture_service import CaptureService
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
    execution_lock: threading.RLock = field(default_factory=threading.RLock)


def create_service_registry() -> ServiceRegistry:
    session = SessionService()
    capture = CaptureService(session)
    actions = ActionService()
    navigation = NavigationService(session)
    observation = ObservationService(session)
    return ServiceRegistry(
        session=session,
        capture=capture,
        actions=actions,
        navigation=navigation,
        observation=observation,
    )

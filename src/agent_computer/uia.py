from __future__ import annotations

import atexit
import importlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Mapping, Protocol

from agent_computer.display import validate_window_preconditions


SUPPORTED_ACTIONS = frozenset(
    {"invoke", "set_value", "toggle", "select", "expand", "collapse", "focus"}
)
SUPPORTED_SCOPES = frozenset({"element", "children", "descendants", "subtree"})
SUPPORTED_LOCATOR_FIELDS = frozenset(
    {
        "name",
        "name_contains",
        "automation_id",
        "class_name",
        "control_type",
        "process_id",
        "enabled",
        "offscreen",
    }
)
MAX_RESULTS = 100
MAX_TRAVERSED_NODES = 10_000


class UIAutomationError(RuntimeError):
    """Base error for Windows UI Automation operations."""


class UIAutomationUnavailableError(UIAutomationError):
    """Raised when Windows UI Automation cannot be initialized."""


class UIAElementNotFoundError(UIAutomationError):
    """Raised when a requested UI Automation root cannot be resolved."""


class UIAStaleElementReferenceError(UIAutomationError):
    """Raised when a runtime ID no longer resolves inside its window."""


class UnsupportedUIAActionError(UIAutomationError):
    """Raised when an action has no safe UIA control-pattern implementation."""


class _UIABackend(Protocol):
    name: str

    def locate(
        self,
        *,
        window_handle: int,
        locator: dict[str, object],
        scope: str,
        max_results: int,
    ) -> list[dict[str, object]]: ...

    def observe(self, node_ref: dict[str, object]) -> dict[str, object]: ...

    def act(
        self,
        node_ref: dict[str, object],
        *,
        action: str,
        value: object | None,
    ) -> dict[str, object]: ...


PreconditionValidator = Callable[..., dict[str, object]]
_DEFAULT_BACKEND: _UIABackend | None = None
_DEFAULT_BACKEND_LOCK = threading.Lock()


def _require_int(value: object, *, name: str, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise UIAutomationError(f"{name} must be an integer.")
    if positive and value <= 0:
        raise UIAutomationError(f"{name} must be greater than zero.")
    return value


def _require_text(value: object, *, name: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise UIAutomationError(f"{name} must be a string.")
    text = value if allow_empty else value.strip()
    if not allow_empty and not text:
        raise UIAutomationError(f"{name} must not be empty.")
    return text


def _normalize_locator(locator: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(locator, Mapping):
        raise UIAutomationError("locator must be a mapping.")
    unknown = set(locator) - SUPPORTED_LOCATOR_FIELDS
    if unknown:
        fields = ", ".join(sorted(str(field) for field in unknown))
        raise UIAutomationError(f"Unsupported UIA locator fields: {fields}.")

    result: dict[str, object] = {}
    for key, value in locator.items():
        if key in {"name", "name_contains", "automation_id", "class_name"}:
            result[key] = _require_text(value, name=f"locator.{key}")
        elif key == "control_type":
            if isinstance(value, str):
                result[key] = _require_text(value, name="locator.control_type")
            else:
                result[key] = _require_int(
                    value, name="locator.control_type", positive=True
                )
        elif key == "process_id":
            result[key] = _require_int(value, name="locator.process_id", positive=True)
        elif key in {"enabled", "offscreen"}:
            if not isinstance(value, bool):
                raise UIAutomationError(f"locator.{key} must be a boolean.")
            result[key] = value
    return result


def _normalize_node_ref(node_ref: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(node_ref, Mapping):
        raise UIAutomationError("node_ref must be a mapping.")
    backend = node_ref.get("backend")
    if backend != "uia":
        raise UIAutomationError("node_ref.backend must be 'uia'.")
    runtime_id = node_ref.get("runtime_id")
    if not isinstance(runtime_id, (list, tuple)) or not runtime_id:
        raise UIAutomationError("node_ref.runtime_id must be a non-empty integer list.")
    normalized_runtime_id = [
        _require_int(item, name="node_ref.runtime_id item") for item in runtime_id
    ]
    return {
        "backend": "uia",
        "runtime_id": normalized_runtime_id,
        "window_handle": _require_int(
            node_ref.get("window_handle"),
            name="node_ref.window_handle",
            positive=True,
        ),
    }


def _normalize_verification(
    verify: Mapping[str, object] | None,
) -> dict[str, object] | None:
    if verify is None:
        return None
    if not isinstance(verify, Mapping):
        raise UIAutomationError("verify must be a mapping.")
    unknown = set(verify) - {"property", "equals"}
    if unknown or "property" not in verify or "equals" not in verify:
        raise UIAutomationError("verify must contain exactly 'property' and 'equals'.")
    return {
        "property": _require_text(verify["property"], name="verify.property"),
        "equals": verify["equals"],
    }


class _UiautomationBackend:
    """Run all COM work on one initialized worker thread and return plain data."""

    name = "uia"

    def __init__(self, automation_module: Any) -> None:
        self._auto = automation_module
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="agent-computer-uia"
        )
        self._initialized = False
        self._closed = False
        self._lifecycle_lock = threading.Lock()
        atexit.register(self.close)

    def _run(self, callback: Callable[[], Any]) -> Any:
        with self._lifecycle_lock:
            if self._closed:
                raise UIAutomationUnavailableError(
                    "The UI Automation backend is closed."
                )

        def run_in_com_thread() -> Any:
            if not self._initialized:
                try:
                    self._auto.InitializeUIAutomationInCurrentThread()
                except Exception as exc:
                    raise UIAutomationUnavailableError(
                        f"Unable to initialize Windows UI Automation: {exc}"
                    ) from exc
                self._initialized = True
            return callback()

        try:
            return self._executor.submit(run_in_com_thread).result()
        except UIAutomationError:
            raise
        except Exception as exc:
            raise UIAutomationError(
                f"Windows UI Automation operation failed: {exc}"
            ) from exc

    def close(self) -> None:
        with self._lifecycle_lock:
            if self._closed:
                return
            self._closed = True
        if self._initialized:
            try:
                self._executor.submit(
                    self._auto.UninitializeUIAutomationInCurrentThread
                ).result()
            except Exception:
                pass
        self._executor.shutdown(wait=True, cancel_futures=True)

    @staticmethod
    def _safe_property(control: Any, name: str, default: object = None) -> object:
        try:
            return getattr(control, name)
        except Exception:
            return default

    def _safe_pattern(self, control: Any, pattern_name: str) -> object | None:
        try:
            pattern_id = getattr(self._auto.PatternId, pattern_name)
            return control.GetPattern(pattern_id)
        except Exception:
            return None

    def _controls_for_scope(self, root: Any, scope: str):
        if scope == "element":
            yield root
            return
        if scope == "children":
            yield from root.GetChildren()
            return
        yield from (
            control
            for control, _depth in self._auto.WalkControl(
                root, includeTop=scope == "subtree"
            )
        )

    @staticmethod
    def _normalize_control_type_name(value: object) -> str:
        normalized = (
            str(value or "").strip().casefold().replace("_", "").replace("-", "")
        )
        if normalized.endswith("control"):
            normalized = normalized[: -len("control")]
        return normalized

    def _matches(self, control: Any, locator: Mapping[str, object]) -> bool:
        for key, expected in locator.items():
            if key == "name":
                actual = self._safe_property(control, "Name", "")
                if actual != expected:
                    return False
            elif key == "name_contains":
                actual = str(self._safe_property(control, "Name", "") or "")
                if str(expected).casefold() not in actual.casefold():
                    return False
            elif key == "automation_id":
                if self._safe_property(control, "AutomationId", "") != expected:
                    return False
            elif key == "class_name":
                if self._safe_property(control, "ClassName", "") != expected:
                    return False
            elif key == "control_type":
                actual_id = self._safe_property(control, "ControlType", 0)
                if isinstance(expected, int):
                    if actual_id != expected:
                        return False
                else:
                    candidates = {
                        self._normalize_control_type_name(
                            self._safe_property(control, "ControlTypeName", "")
                        ),
                        self._normalize_control_type_name(
                            self._safe_property(control, "LocalizedControlType", "")
                        ),
                    }
                    if self._normalize_control_type_name(expected) not in candidates:
                        return False
            elif key == "process_id":
                if self._safe_property(control, "ProcessId", 0) != expected:
                    return False
            elif key == "enabled":
                if self._safe_property(control, "IsEnabled", False) is not expected:
                    return False
            elif key == "offscreen":
                if self._safe_property(control, "IsOffscreen", True) is not expected:
                    return False
        return True

    @staticmethod
    def _rect_payload(rect: object) -> dict[str, int] | None:
        try:
            left = int(getattr(rect, "left"))
            top = int(getattr(rect, "top"))
            right = int(getattr(rect, "right"))
            bottom = int(getattr(rect, "bottom"))
        except (AttributeError, TypeError, ValueError):
            return None
        return {
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
            "width": max(0, right - left),
            "height": max(0, bottom - top),
        }

    def _snapshot(self, control: Any, *, window_handle: int) -> dict[str, object]:
        try:
            runtime_id = [int(item) for item in control.GetRuntimeId()]
        except Exception as exc:
            raise UIAutomationError(
                "The UI Automation element did not expose a usable runtime ID."
            ) from exc
        if not runtime_id:
            raise UIAutomationError(
                "The UI Automation element returned an empty runtime ID."
            )

        clickable_point: dict[str, int] | None = None
        try:
            click_x, click_y, clickable = control.GetClickablePoint()
            if clickable:
                clickable_point = {"x": int(click_x), "y": int(click_y)}
        except Exception:
            pass

        is_password = bool(self._safe_property(control, "IsPassword", False))
        patterns: list[str] = []
        pattern_objects: dict[str, object] = {}
        for name, pattern_name in (
            ("invoke", "InvokePattern"),
            ("value", "ValuePattern"),
            ("toggle", "TogglePattern"),
            ("selection_item", "SelectionItemPattern"),
            ("expand_collapse", "ExpandCollapsePattern"),
        ):
            pattern = self._safe_pattern(control, pattern_name)
            if pattern is not None:
                patterns.append(name)
                pattern_objects[name] = pattern

        value: object | None = None
        value_redacted = False
        if "value" in pattern_objects:
            if is_password:
                value_redacted = True
            else:
                try:
                    value = str(getattr(pattern_objects["value"], "Value"))
                except Exception:
                    value = None

        native_handle = self._safe_property(control, "NativeWindowHandle", 0)
        return {
            "nodeRef": {
                "backend": "uia",
                "runtime_id": runtime_id,
                "window_handle": window_handle,
            },
            "name": str(self._safe_property(control, "Name", "") or ""),
            "automation_id": str(
                self._safe_property(control, "AutomationId", "") or ""
            ),
            "control_type": int(self._safe_property(control, "ControlType", 0) or 0),
            "control_type_name": str(
                self._safe_property(control, "ControlTypeName", "") or ""
            ),
            "localized_control_type": str(
                self._safe_property(control, "LocalizedControlType", "") or ""
            ),
            "class_name": str(self._safe_property(control, "ClassName", "") or ""),
            "process_id": int(self._safe_property(control, "ProcessId", 0) or 0),
            "native_window_handle": int(native_handle or 0),
            "bounds": self._rect_payload(
                self._safe_property(control, "BoundingRectangle")
            ),
            "clickable_point": clickable_point,
            "enabled": bool(self._safe_property(control, "IsEnabled", False)),
            "offscreen": bool(self._safe_property(control, "IsOffscreen", True)),
            "keyboard_focusable": bool(
                self._safe_property(control, "IsKeyboardFocusable", False)
            ),
            "has_keyboard_focus": bool(
                self._safe_property(control, "HasKeyboardFocus", False)
            ),
            "is_password": is_password,
            "value": value,
            "value_redacted": value_redacted,
            "patterns": patterns,
        }

    def _root_for_window(self, window_handle: int) -> Any:
        root = self._auto.ControlFromHandle(window_handle)
        if root is None:
            raise UIAElementNotFoundError(
                f"UI Automation could not resolve window handle {window_handle}."
            )
        return root

    def _resolve_control(self, node_ref: Mapping[str, object]) -> Any:
        window_handle = int(node_ref["window_handle"])
        expected_runtime_id = tuple(int(item) for item in node_ref["runtime_id"])
        root = self._root_for_window(window_handle)
        traversed = 0
        for control, _depth in self._auto.WalkControl(root, includeTop=True):
            traversed += 1
            if traversed > MAX_TRAVERSED_NODES:
                break
            try:
                runtime_id = tuple(int(item) for item in control.GetRuntimeId())
            except Exception:
                continue
            if runtime_id == expected_runtime_id:
                return control
        raise UIAStaleElementReferenceError(
            "The UI Automation element is stale or no longer belongs to its window."
        )

    def locate(
        self,
        *,
        window_handle: int,
        locator: dict[str, object],
        scope: str,
        max_results: int,
    ) -> list[dict[str, object]]:
        def locate_in_worker() -> list[dict[str, object]]:
            root = self._root_for_window(window_handle)
            matches: list[dict[str, object]] = []
            traversed = 0
            for control in self._controls_for_scope(root, scope):
                traversed += 1
                if traversed > MAX_TRAVERSED_NODES:
                    raise UIAutomationError(
                        "UI Automation traversal exceeded 10000 elements; use a narrower window or locator."
                    )
                if self._matches(control, locator):
                    matches.append(self._snapshot(control, window_handle=window_handle))
                    if len(matches) >= max_results:
                        break
            return matches

        return self._run(locate_in_worker)

    def observe(self, node_ref: dict[str, object]) -> dict[str, object]:
        def observe_in_worker() -> dict[str, object]:
            control = self._resolve_control(node_ref)
            return self._snapshot(control, window_handle=int(node_ref["window_handle"]))

        return self._run(observe_in_worker)

    def act(
        self,
        node_ref: dict[str, object],
        *,
        action: str,
        value: object | None,
    ) -> dict[str, object]:
        def act_in_worker() -> dict[str, object]:
            control = self._resolve_control(node_ref)
            pattern_name: str | None = None
            performed = False
            if action == "focus":
                performed = bool(control.SetFocus())
            elif action == "invoke":
                pattern_name = "InvokePattern"
                pattern = self._safe_pattern(control, pattern_name)
                if pattern is not None:
                    performed = bool(pattern.Invoke(waitTime=0))
            elif action == "set_value":
                pattern_name = "ValuePattern"
                pattern = self._safe_pattern(control, pattern_name)
                if pattern is not None:
                    performed = bool(pattern.SetValue(str(value), waitTime=0))
            elif action == "toggle":
                pattern_name = "TogglePattern"
                pattern = self._safe_pattern(control, pattern_name)
                if pattern is not None:
                    performed = bool(pattern.Toggle(waitTime=0))
            elif action == "select":
                pattern_name = "SelectionItemPattern"
                pattern = self._safe_pattern(control, pattern_name)
                if pattern is not None:
                    performed = bool(pattern.Select(waitTime=0))
            elif action in {"expand", "collapse"}:
                pattern_name = "ExpandCollapsePattern"
                pattern = self._safe_pattern(control, pattern_name)
                if pattern is not None:
                    method = pattern.Expand if action == "expand" else pattern.Collapse
                    performed = bool(method(waitTime=0))

            if not performed:
                requirement = pattern_name or "keyboard focus support"
                raise UnsupportedUIAActionError(
                    f"Element does not support {requirement} for UIA action {action!r}."
                )
            return {
                "performed": True,
                "pattern": "focus" if pattern_name is None else pattern_name,
            }

        return self._run(act_in_worker)


def _load_default_backend() -> _UIABackend:
    global _DEFAULT_BACKEND

    with _DEFAULT_BACKEND_LOCK:
        if _DEFAULT_BACKEND is not None:
            return _DEFAULT_BACKEND

        _DEFAULT_BACKEND = _create_default_backend()
        return _DEFAULT_BACKEND


def _create_default_backend() -> _UIABackend:
    if os.name != "nt":
        raise UIAutomationUnavailableError(
            "Windows UI Automation is only available on Windows."
        )
    try:
        automation_module = importlib.import_module("uiautomation")
    except ModuleNotFoundError as exc:
        raise UIAutomationUnavailableError(
            "Windows UI Automation requires the optional 'uiautomation' dependency. "
            "Install the project on Windows or run: pip install 'uiautomation>=2.0.29,<3'."
        ) from exc
    except Exception as exc:
        raise UIAutomationUnavailableError(
            f"Unable to import the Windows UI Automation dependency: {exc}"
        ) from exc
    try:
        return _UiautomationBackend(automation_module)
    except Exception as exc:
        raise UIAutomationUnavailableError(
            f"Unable to initialize the Windows UI Automation backend: {exc}"
        ) from exc


class UIAClient:
    """JSON-friendly, window-scoped locate/observe/act facade for Windows UIA."""

    def __init__(
        self,
        backend: _UIABackend | None = None,
        *,
        precondition_validator: PreconditionValidator | None = None,
    ) -> None:
        self._backend = backend
        self._precondition_validator = (
            precondition_validator or validate_window_preconditions
        )

    @property
    def backend(self) -> _UIABackend:
        if self._backend is None:
            self._backend = _load_default_backend()
        return self._backend

    def locate(
        self,
        *,
        window_handle: int,
        locator: Mapping[str, object],
        scope: str = "descendants",
        max_results: int = 20,
    ) -> dict[str, object]:
        hwnd = _require_int(window_handle, name="window_handle", positive=True)
        normalized_locator = _normalize_locator(locator)
        if scope not in SUPPORTED_SCOPES:
            raise UIAutomationError(
                f"scope must be one of: {', '.join(sorted(SUPPORTED_SCOPES))}."
            )
        limit = _require_int(max_results, name="max_results", positive=True)
        if limit > MAX_RESULTS:
            raise UIAutomationError(f"max_results must not exceed {MAX_RESULTS}.")
        matches = self.backend.locate(
            window_handle=hwnd,
            locator=normalized_locator,
            scope=scope,
            max_results=limit,
        )
        return {
            "backend": "uia",
            "window_handle": hwnd,
            "locator": normalized_locator,
            "scope": scope,
            "count": len(matches),
            "matches": matches,
        }

    def observe(self, node_ref: Mapping[str, object]) -> dict[str, object]:
        normalized_ref = _normalize_node_ref(node_ref)
        element = self.backend.observe(normalized_ref)
        return {"backend": "uia", "element": element}

    def act(
        self,
        node_ref: Mapping[str, object],
        *,
        action: str,
        value: object | None = None,
        verify: Mapping[str, object] | None = None,
        expected_bounds: object | None = None,
        layout_version: str | None = None,
    ) -> dict[str, object]:
        normalized_ref = _normalize_node_ref(node_ref)
        normalized_action = _require_text(action, name="action").casefold()
        if normalized_action not in SUPPORTED_ACTIONS:
            raise UnsupportedUIAActionError(
                f"Unsupported UIA action {action!r}; supported actions are: "
                f"{', '.join(sorted(SUPPORTED_ACTIONS))}."
            )
        if normalized_action == "set_value" and value is None:
            raise UIAutomationError("set_value requires a value.")
        if normalized_action != "set_value" and value is not None:
            raise UIAutomationError(
                f"UIA action {normalized_action!r} does not accept a value."
            )
        if normalized_action == "set_value" and not isinstance(value, str):
            raise UIAutomationError("set_value requires a string value.")
        normalized_verification = _normalize_verification(verify)

        precondition_arguments: dict[str, object] = {
            "expected_hwnd": normalized_ref["window_handle"]
        }
        if expected_bounds is not None:
            precondition_arguments["bounds"] = expected_bounds
        if layout_version is not None:
            precondition_arguments["layout_version"] = layout_version
        preconditions = self._precondition_validator(**precondition_arguments)

        action_result = self.backend.act(
            normalized_ref, action=normalized_action, value=value
        )
        verification_status = "not_requested"
        verification_result: dict[str, object] | None = None
        observed: dict[str, object] | None = None
        if normalized_verification is not None:
            property_name = str(normalized_verification["property"])
            observed = self.backend.observe(normalized_ref)
            actual = observed.get(property_name)
            expected = normalized_verification["equals"]
            verification_status = "passed" if actual == expected else "failed"
            verification_result = {
                "property": property_name,
                "expected": expected,
                "actual": actual,
            }

        return {
            "backend": "uia",
            "nodeRef": normalized_ref,
            "action": normalized_action,
            "performed": bool(action_result.get("performed", False)),
            "actionResult": action_result,
            "preconditions": preconditions,
            "verificationStatus": verification_status,
            "verification": verification_result,
            "observed": observed,
        }


def locate_element(
    *,
    window_handle: int,
    locator: Mapping[str, object],
    scope: str = "descendants",
    max_results: int = 20,
    _backend: _UIABackend | None = None,
) -> dict[str, object]:
    return UIAClient(backend=_backend).locate(
        window_handle=window_handle,
        locator=locator,
        scope=scope,
        max_results=max_results,
    )


def observe_element(
    node_ref: Mapping[str, object], *, _backend: _UIABackend | None = None
) -> dict[str, object]:
    return UIAClient(backend=_backend).observe(node_ref)


def act_on_element(
    node_ref: Mapping[str, object],
    *,
    action: str,
    value: object | None = None,
    verify: Mapping[str, object] | None = None,
    expected_bounds: object | None = None,
    layout_version: str | None = None,
    _backend: _UIABackend | None = None,
) -> dict[str, object]:
    return UIAClient(backend=_backend).act(
        node_ref,
        action=action,
        value=value,
        verify=verify,
        expected_bounds=expected_bounds,
        layout_version=layout_version,
    )

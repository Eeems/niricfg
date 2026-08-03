# pyright: reportPrivateImportUsage=false
import math
import os
import re
import tempfile
import traceback
from typing import ClassVar, Protocol, cast

import flet as ft
import kdl

AnimationConfig = dict[str, str | int | float | list[float] | None]

# Generic spring defaults from niri, used when a spring node omits a property.
SPRING_DAMPING_RATIO = 1.0
SPRING_STIFFNESS = 1000
SPRING_EPSILON = 0.0001

# Niri config directory, honoring XDG_CONFIG_HOME with ~/.config fallback.
NIRI_CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
    "niri",
)


# From niri-config/src/animations.rs
NIRI_DEFAULTS: dict[str, AnimationConfig] = {
    "workspace-switch": {
        "kind": "spring",
        "damping_ratio": 1.0,
        "stiffness": 1000,
        "epsilon": 0.0001,
    },
    "window-open": {
        "kind": "easing",
        "duration_ms": 150,
        "curve": "ease-out-expo",
        "bezier": None,
    },
    "window-close": {
        "kind": "easing",
        "duration_ms": 150,
        "curve": "ease-out-quad",
        "bezier": None,
    },
    "horizontal-view-movement": {
        "kind": "spring",
        "damping_ratio": 1.0,
        "stiffness": 800,
        "epsilon": 0.0001,
    },
    "window-movement": {
        "kind": "spring",
        "damping_ratio": 1.0,
        "stiffness": 800,
        "epsilon": 0.0001,
    },
    "window-resize": {
        "kind": "spring",
        "damping_ratio": 1.0,
        "stiffness": 800,
        "epsilon": 0.0001,
    },
    "config-notification-open-close": {
        "kind": "spring",
        "damping_ratio": 0.6,
        "stiffness": 1000,
        "epsilon": 0.001,
    },
    "exit-confirmation-open-close": {
        "kind": "spring",
        "damping_ratio": 0.6,
        "stiffness": 500,
        "epsilon": 0.01,
    },
    "screenshot-ui-open": {
        "kind": "easing",
        "duration_ms": 200,
        "curve": "ease-out-quad",
        "bezier": None,
    },
    "overview-open-close": {
        "kind": "spring",
        "damping_ratio": 1.0,
        "stiffness": 800,
        "epsilon": 0.0001,
    },
    "recent-windows-close": {
        "kind": "spring",
        "damping_ratio": 1.0,
        "stiffness": 800,
        "epsilon": 0.001,
    },
}


class KDLNode(Protocol):
    name: str
    args: list[object]
    props: dict[str, object]
    nodes: list["KDLNode"]


@ft.control
class AnimationsTab(ft.Container):
    ANIMATIONS: ClassVar[list[str]] = [
        "workspace-switch",
        "window-open",
        "window-close",
        "horizontal-view-movement",
        "window-movement",
        "window-resize",
        "config-notification-open-close",
        "exit-confirmation-open-close",
        "screenshot-ui-open",
        "overview-open-close",
        "recent-windows-close",
    ]
    SLOWDOWN_MIN: ClassVar[float] = 0.1
    SLOWDOWN_MAX: ClassVar[float] = 2.0
    CARD_WIDTH: ClassVar[int] = 560
    CARD_SPACING: ClassVar[int] = 16

    def __init__(self) -> None:
        self.global_off_switch: ft.Switch = ft.Switch(
            label="Disable all animations",
            on_change=lambda _: self.on_global_off_change(),
        )
        self.slowdown_slider: ft.Slider = ft.Slider(
            min=AnimationsTab.SLOWDOWN_MIN,
            max=AnimationsTab.SLOWDOWN_MAX,
            value=1.0,
            divisions=19,
            width=AnimationsTab.CARD_WIDTH,
            label="Slowdown",
            on_change=lambda _: self.on_slider_change(),
        )
        self.slowdown_input: ft.TextField = ft.TextField(
            label="Slowdown",
            value="1.0",
            width=105,
            on_blur=lambda _: self.on_input_change(),
            on_submit=lambda _: self.on_input_change(),
        )
        self.status_text: ft.Text = ft.Text("", size=14, color="gray")
        self.dropdowns: dict[str, ft.Dropdown] = {}
        self.kind_inputs: dict[str, ft.Dropdown] = {}
        self.duration_inputs: dict[str, ft.TextField] = {}
        self.curve_inputs: dict[str, ft.Dropdown] = {}
        self.bezier_inputs: dict[str, ft.TextField] = {}
        self.damping_inputs: dict[str, ft.TextField] = {}
        self.stiffness_inputs: dict[str, ft.TextField] = {}
        self.epsilon_inputs: dict[str, ft.TextField] = {}
        self.easing_rows: dict[str, ft.Row] = {}
        self.spring_rows: dict[str, ft.Row] = {}
        self.preset_configs: dict[str, dict[str, AnimationConfig | None]] = {}
        self._parse_errors: set[str] = set()

        for name in AnimationsTab.ANIMATIONS:
            self.dropdowns[name] = ft.Dropdown(
                options=[],
                width=400,
                on_select=lambda e, name=name: self.on_animation_select(name, e),
            )
            self.kind_inputs[name] = ft.Dropdown(
                label="Type",
                options=[
                    ft.dropdown.Option(key="easing", text="Easing"),
                    ft.dropdown.Option(key="spring", text="Spring"),
                ],
                width=140,
                on_select=lambda e, name=name: self.on_kind_select(name, e),
            )
            self.duration_inputs[name] = ft.TextField(
                label="Duration",
                hint_text="ms",
                width=110,
                keyboard_type=ft.KeyboardType.NUMBER,
                on_change=lambda _: self.mark_pending(),
            )
            self.curve_inputs[name] = ft.Dropdown(
                label="Curve",
                options=[
                    ft.dropdown.Option(key=curve, text=curve)
                    for curve in [
                        "linear",
                        "ease-out-quad",
                        "ease-out-cubic",
                        "ease-out-expo",
                        "cubic-bezier",
                    ]
                ],
                width=200,
                on_select=lambda e, name=name: self.on_curve_select(name, e),
            )
            self.damping_inputs[name] = ft.TextField(
                label="Damping",
                width=110,
                on_change=lambda _: self.mark_pending(),
            )
            self.stiffness_inputs[name] = ft.TextField(
                label="Stiffness",
                width=100,
                on_change=lambda _: self.mark_pending(),
            )
            self.epsilon_inputs[name] = ft.TextField(
                label="Epsilon",
                width=110,
                on_change=lambda _: self.mark_pending(),
            )
            self.bezier_inputs[name] = ft.TextField(
                label="Bezier",
                hint_text="x1 y1 x2 y2",
                width=180,
                on_change=lambda _: self.mark_pending(),
            )
            self.easing_rows[name] = ft.Row(
                [
                    self.duration_inputs[name],
                    self.curve_inputs[name],
                    self.bezier_inputs[name],
                ],
                spacing=10,
            )
            self.spring_rows[name] = ft.Row(
                [
                    self.damping_inputs[name],
                    self.stiffness_inputs[name],
                    self.epsilon_inputs[name],
                ],
                spacing=10,
            )

        self.cards: dict[str, ft.Container] = {
            name: ft.Container(
                width=AnimationsTab.CARD_WIDTH,
                margin=ft.Margin(0, 0, 0, AnimationsTab.CARD_SPACING),
                content=ft.Column(
                    [
                        ft.Text(
                            name,
                            size=12,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Row(
                            [self.dropdowns[name], self.kind_inputs[name]],
                            spacing=10,
                        ),
                        self.easing_rows[name],
                        self.spring_rows[name],
                    ],
                    spacing=8,
                ),
            )
            for name in AnimationsTab.ANIMATIONS
        }
        self.grid: ft.Column = ft.Column(
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        self._armed: bool = False
        self._reset_armed: bool = False
        self._held_modifiers: set[str] = set()
        self._kb_listener: ft.KeyboardListener

        kb_listener = ft.KeyboardListener(
            autofocus=True,
            on_key_down=self.on_key_down,
            on_key_up=self.on_key_up,
            content=ft.Column(
                [
                    self.status_text,
                    ft.Divider(),
                    self.global_off_switch,
                    ft.Text("Slowdown", size=12, weight=ft.FontWeight.BOLD),
                    self.slowdown_slider,
                    ft.Row(
                        [self.slowdown_input],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Divider(),
                    self.grid,
                    ft.Divider(),
                    ft.Row(
                        [
                            ft.Button("Save", on_click=lambda _: self.on_apply()),
                            ft.Button("Reset", on_click=lambda _: self.on_reset()),
                        ],
                        spacing=10,
                    ),
                ],
                spacing=16,
                expand=True,
            ),
        )
        self._kb_listener = kb_listener

        super().__init__(
            content=kb_listener,
            expand=True,
            padding=10,
        )

    def _modifier_name(self, key: str) -> str | None:
        lower = key.lower()
        for name in ("control", "shift", "alt", "meta"):
            if name in lower:
                return name
        return None

    def on_key_down(self, e: ft.KeyDownEvent) -> None:
        modifier = self._modifier_name(e.key)
        if modifier is not None:
            self._held_modifiers.add(modifier)
            self._armed = False
            self._reset_armed = False
        elif e.key.lower() == "s":
            self._armed = self._held_modifiers == {"control"}
            self._reset_armed = False
        elif e.key.lower() == "z":
            self._reset_armed = self._held_modifiers == {"control"}
            self._armed = False
        else:
            self._armed = False
            self._reset_armed = False

    def on_key_up(self, e: ft.KeyUpEvent) -> None:
        modifier = self._modifier_name(e.key)
        if modifier is not None:
            self._held_modifiers.discard(modifier)
        elif e.key.lower() == "s" and self._armed and self._held_modifiers == {"control"}:
            self._armed = False
            self.on_apply()
        elif (
            e.key.lower() == "z"
            and self._reset_armed
            and self._held_modifiers == {"control"}
        ):
            self._reset_armed = False
            self.on_reset()

    def focus_keyboard(self) -> None:
        if self.page:
            _ = self.page.run_task(self._kb_listener.focus)

    def relayout(self) -> None:
        width = self.page.width if self.page else None
        if not width:
            return
        available = width - 20  # container padding
        cols = int(
            (available + AnimationsTab.CARD_SPACING)
            // (AnimationsTab.CARD_WIDTH + AnimationsTab.CARD_SPACING)
        )
        cols = max(1, cols)
        self.grid.controls = [
            ft.Row(
                [self.cards[name] for name in AnimationsTab.ANIMATIONS[i : i + cols]],
                spacing=AnimationsTab.CARD_SPACING,
            )
            for i in range(0, len(AnimationsTab.ANIMATIONS), cols)
        ]
        self.grid.update()

    def set_status(self, message: str, color: str = "gray") -> None:
        self.status_text.value = message
        self.status_text.color = color
        self.status_text.update()

    def mark_pending(self) -> None:
        self.set_status("Pending changes", "orange")

    def parse_float(self, value: str | None) -> float | None:
        if value is None or str(value).strip() == "":
            return None
        try:
            result = float(value)
        except ValueError:
            traceback.print_exc()
            return None
        if not math.isfinite(result):
            return None
        return result

    def parse_int(self, value: str | None) -> int | None:
        if value is None or str(value).strip() == "":
            return None
        try:
            return int(value)
        except ValueError:
            traceback.print_exc()
            return None

    def parse_bezier(self, name: str) -> list[float] | None:
        value = self.bezier_inputs[name].value
        if not value:
            return None
        parts = value.split()
        if len(parts) != 4:
            return None
        try:
            return [float(p) for p in parts]
        except ValueError:
            traceback.print_exc()
            return None

    def parse_animation_node(self, node: KDLNode) -> AnimationConfig | None:
        spring = next((c for c in node.nodes if c.name == "spring"), None)
        if spring is not None:
            props = spring.props
            return {
                "kind": "spring",
                "damping_ratio": float(
                    cast(
                        int | float | str,
                        props.get("damping-ratio", SPRING_DAMPING_RATIO),
                    )
                ),
                "stiffness": int(
                    cast(int | float | str, props.get("stiffness", SPRING_STIFFNESS))
                ),
                "epsilon": float(
                    cast(int | float | str, props.get("epsilon", SPRING_EPSILON))
                ),
            }

        duration = next((c for c in node.nodes if c.name == "duration-ms"), None)
        curve = next((c for c in node.nodes if c.name == "curve"), None)
        if duration is None and curve is None:
            return None

        config: AnimationConfig = {
            "kind": "easing",
            "duration_ms": None,
            "curve": None,
            "bezier": None,
        }
        if duration is not None and duration.args:
            config["duration_ms"] = int(cast(int | float | str, duration.args[0]))
        if curve is not None and curve.args:
            config["curve"] = str(curve.args[0])
            if config["curve"] == "cubic-bezier" and len(curve.args) >= 5:
                config["bezier"] = [
                    float(a) for a in cast(list[int | float | str], curve.args[1:5])
                ]
        return config

    def resolve_preset_path(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.join(NIRI_CONFIG_DIR, path)

    def preset_config(self, name: str, path: str) -> AnimationConfig | None:
        try:
            with open(self.resolve_preset_path(path)) as f:
                doc = kdl.parse(f.read())
            for node in cast(list[KDLNode], doc.nodes):
                if node.name == "animations":
                    for child in node.nodes:
                        if child.name == name:
                            return self.parse_animation_node(child)
        except Exception:
            traceback.print_exc()
        return None

    def _skip_string(self, text: str, quote_idx: int) -> int:
        raw = False
        hashes = 0
        j = quote_idx - 1
        while j >= 0 and text[j] == "#":
            hashes += 1
            j -= 1
        if j >= 0 and text[j] in ("r", "R"):
            raw = True
        n = len(text)
        i = quote_idx + 1
        while i < n:
            if text[i] == '"':
                if raw:
                    k = i + 1
                    while k < n and text[k] == "#":
                        k += 1
                    if k - i - 1 == hashes and (
                        k == n or text[k] in (" ", "\t", "\n", "\r", "}", ";")
                    ):
                        return k
                    i += 1
                    continue
                if i > 0:
                    k = i - 1
                    while k >= 0 and text[k] == "\\":
                        k -= 1
                    if (i - 1 - k) % 2 == 1:
                        i += 1
                        continue
                return i + 1
            i += 1
        return n

    def _skip_comment(self, text: str, i: int) -> int | None:
        n = len(text)
        if i + 1 >= n or text[i] != "/":
            return None
        if text[i + 1] == "/":
            j = text.find("\n", i)
            return j if j != -1 else n
        if text[i + 1] == "*":
            j = text.find("*/", i + 2)
            return j + 2 if j != -1 else n
        return None

    def _brace_depth(self, text: str) -> int:
        depth = 0
        i = 0
        n = len(text)
        while i < n:
            if text[i] == '"':
                i = self._skip_string(text, i)
                continue
            if text[i] == "/":
                j = self._skip_comment(text, i)
                if j is not None:
                    i = j
                    continue
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        return depth

    def _find_matching_brace(self, text: str, open_idx: int) -> int | None:
        depth = 0
        i = open_idx
        n = len(text)
        while i < n:
            if text[i] == '"':
                i = self._skip_string(text, i)
                continue
            if text[i] == "/":
                j = self._skip_comment(text, i)
                if j is not None:
                    i = j
                    continue
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return i
            i += 1
        return None

    def _find_node_text(self, name: str, text: str, depth: int = 1) -> str | None:
        pattern = re.compile(r"^[ \t]*" + re.escape(name) + r"[ \t]*\{", re.MULTILINE)
        for m in pattern.finditer(text):
            if self._brace_depth(text[: m.start()]) != depth:
                continue
            close_idx = self._find_matching_brace(text, m.end() - 1)
            if close_idx is None:
                continue
            return text[m.start() : close_idx + 1]
        return None

    def extract_animation_node_text(self, name: str, path: str) -> str | None:
        try:
            with open(self.resolve_preset_path(path)) as f:
                text = f.read()
        except Exception:
            traceback.print_exc()
            return None
        return self._find_node_text(name, text)

    def base_config(self, name: str) -> AnimationConfig | None:
        choice = self.dropdowns[name].value
        if choice in (None, "", "__default__"):
            return NIRI_DEFAULTS[name]
        if choice == "off":
            return None
        return self.preset_configs.get(name, {}).get(choice) or NIRI_DEFAULTS[name]

    def current_config(self, name: str) -> AnimationConfig:
        if (self.kind_inputs[name].value or "easing") == "spring":
            return {
                "kind": "spring",
                "damping_ratio": self.parse_float(self.damping_inputs[name].value),
                "stiffness": self.parse_int(self.stiffness_inputs[name].value),
                "epsilon": self.parse_float(self.epsilon_inputs[name].value),
            }
        return {
            "kind": "easing",
            "duration_ms": self.parse_int(self.duration_inputs[name].value),
            "curve": self.curve_inputs[name].value or None,
            "bezier": self.parse_bezier(name),
        }

    def comparable(self, config: AnimationConfig | None) -> AnimationConfig | None:
        if config is None:
            return None
        return dict(config)

    def fill_fields(self, name: str, config: AnimationConfig | None) -> None:
        if config is None:
            self.kind_inputs[name].value = "easing"
            self.duration_inputs[name].value = ""
            self.curve_inputs[name].value = "ease-out-expo"
            self.bezier_inputs[name].value = ""
            self.damping_inputs[name].value = ""
            self.stiffness_inputs[name].value = ""
            self.epsilon_inputs[name].value = ""
            self.update_field_visibility(name)
            return

        kind = cast(str, config["kind"])
        self.kind_inputs[name].value = kind
        if kind == "spring":
            damping = config.get("damping_ratio")
            stiffness = config.get("stiffness")
            epsilon = config.get("epsilon")
            self.damping_inputs[name].value = "" if damping is None else str(damping)
            self.stiffness_inputs[name].value = (
                "" if stiffness is None else str(stiffness)
            )
            self.epsilon_inputs[name].value = "" if epsilon is None else str(epsilon)
        else:
            duration = config.get("duration_ms")
            curve = config.get("curve") or "ease-out-expo"
            bezier = cast(list[float] | None, config.get("bezier"))
            self.duration_inputs[name].value = "" if duration is None else str(duration)
            dropdown = self.curve_inputs[name]
            if not any(opt.key == str(curve) for opt in dropdown.options):
                dropdown.options.append(
                    ft.dropdown.Option(key=str(curve), text=str(curve))
                )
            dropdown.value = str(curve)
            self.bezier_inputs[name].value = (
                "" if not bezier else " ".join(str(b) for b in bezier)
            )
        self.update_field_visibility(name)

    def update_field_visibility(self, name: str) -> None:
        kind = self.kind_inputs[name].value or "easing"
        self.easing_rows[name].visible = kind == "easing"
        self.spring_rows[name].visible = kind == "spring"
        self.easing_rows[name].update()
        self.spring_rows[name].update()
        self.bezier_inputs[name].visible = (
            self.curve_inputs[name].value == "cubic-bezier"
        )
        self.bezier_inputs[name].update()

    def on_global_off_change(self) -> None:
        self.set_disabled_states()
        self.mark_pending()

    def on_animation_select(self, name: str, _e: ft.Event[ft.Dropdown]) -> None:
        # Picking a preset resets the override fields to that preset's values.
        self.fill_fields(name, self.base_config(name))
        self.set_disabled_states()
        self.mark_pending()

    def on_kind_select(self, name: str, _e: ft.Event[ft.Dropdown]) -> None:
        if (
            self.kind_inputs[name].value == "easing"
            and not self.duration_inputs[name].value
            and not self.curve_inputs[name].value
        ):
            self.duration_inputs[name].value = "250"
            self.curve_inputs[name].value = "ease-out-cubic"
        elif self.kind_inputs[name].value == "spring":
            if not self.damping_inputs[name].value:
                self.damping_inputs[name].value = str(SPRING_DAMPING_RATIO)
            if not self.stiffness_inputs[name].value:
                self.stiffness_inputs[name].value = str(SPRING_STIFFNESS)
            if not self.epsilon_inputs[name].value:
                self.epsilon_inputs[name].value = str(SPRING_EPSILON)
        self.update_field_visibility(name)
        self.mark_pending()

    def on_curve_select(self, name: str, _e: ft.Event[ft.Dropdown]) -> None:
        self.update_field_visibility(name)
        self.mark_pending()

    def set_disabled_states(self) -> None:
        global_off = self.animations_off
        for ctrl in [self.slowdown_slider, self.slowdown_input]:
            ctrl.disabled = global_off
            ctrl.update()
        for name, dropdown in self.dropdowns.items():
            off = global_off or (dropdown.value == "off")
            is_default = dropdown.value in (None, "", "__default__")
            dropdown.disabled = global_off
            dropdown.update()
            kind = self.kind_inputs[name]
            kind.disabled = off or not is_default
            kind.update()
            controls = list(self.easing_rows[name].controls)
            controls.extend(self.spring_rows[name].controls)
            for ctrl in controls:
                ctrl.disabled = off
                ctrl.update()

    def refresh(self) -> None:
        presets: dict[str, list[str]] = {}
        self.preset_configs = {}
        for name in AnimationsTab.ANIMATIONS:
            by_name: dict[str, str] = {}
            # System dir first, user dir last, so a user preset with the same
            # filename wins over the system one. System presets keep their
            # absolute path; user presets use a path relative to animations.kdl.
            for preset_dir, is_system in (
                ("/usr/share/niri/animations", True),
                (os.path.join(NIRI_CONFIG_DIR, "animations"), False),
            ):
                anim_dir = os.path.join(preset_dir, name)
                if not os.path.isdir(anim_dir):
                    continue
                for f in sorted(os.listdir(anim_dir)):
                    if f.endswith(".kdl"):
                        if is_system:
                            by_name[f] = os.path.join(anim_dir, f)
                        else:
                            by_name[f] = os.path.join("animations", name, f)
            presets[name] = list(by_name.values())
            self.preset_configs[name] = {
                path: self.preset_config(name, path) for path in by_name.values()
            }

        self.set_presets(presets)
        self.relayout()
        animations_off, slowdown, selections, overrides = self.read_animations_kdl()
        self.set_state(animations_off, slowdown, selections, overrides)
        _ = self._report_parse_errors()
        self.update()

    def set_presets(self, presets: dict[str, list[str]]) -> None:
        for name in AnimationsTab.ANIMATIONS:
            dropdown = self.dropdowns[name]
            options = [
                ft.dropdown.Option(key="__default__", text="Default"),
                ft.dropdown.Option(key="off", text="Off"),
            ]
            for path in presets.get(name, []):
                label = os.path.splitext(os.path.basename(path))[0]
                options.append(ft.dropdown.Option(key=path, text=label))
            dropdown.options = options

    def set_state(
        self,
        animations_off: bool,
        slowdown: float | None,
        selections: dict[str, str | None],
        overrides: dict[str, AnimationConfig | None],
    ) -> None:
        self.global_off_switch.value = animations_off
        if slowdown is None:
            slowdown = 1.0
        value = round(
            max(AnimationsTab.SLOWDOWN_MIN, min(AnimationsTab.SLOWDOWN_MAX, slowdown)),
            2,
        )
        self.slowdown_slider.value = value
        self.slowdown_input.value = str(value)
        for name, dropdown in self.dropdowns.items():
            available = {opt.key for opt in dropdown.options}
            choice = selections.get(name)
            if choice in available:
                dropdown.value = choice
            else:
                dropdown.value = "__default__"
        for name in AnimationsTab.ANIMATIONS:
            config = overrides.get(name)
            if config is None:
                config = self.base_config(name)
            self.fill_fields(name, config)
        self.set_disabled_states()

    @property
    def animations_off(self) -> bool:
        return bool(self.global_off_switch.value)

    @property
    def slowdown_value(self) -> float:
        return self.slowdown_slider.value or 1.0

    def on_slider_change(self) -> None:
        self.slowdown_input.value = str(
            round(
                max(
                    AnimationsTab.SLOWDOWN_MIN,
                    min(AnimationsTab.SLOWDOWN_MAX, self.slowdown_value),
                ),
                2,
            )
        )
        self.slowdown_input.update()
        self.mark_pending()

    def on_input_change(self) -> None:
        try:
            value = round(
                max(
                    AnimationsTab.SLOWDOWN_MIN,
                    min(AnimationsTab.SLOWDOWN_MAX, float(self.slowdown_input.value)),
                ),
                2,
            )

        except (ValueError, TypeError):
            traceback.print_exc()
            value = self.slowdown_value

        self.slowdown_slider.value = value
        self.slowdown_input.value = str(value)
        self.slowdown_slider.update()
        self.slowdown_input.update()
        self.mark_pending()

    def selections(self) -> dict[str, str | None]:
        result: dict[str, str | None] = {}
        for name, dropdown in self.dropdowns.items():
            value = dropdown.value
            if value in (None, "", "__default__"):
                result[name] = None
            elif value == "off":
                result[name] = "off"
            else:
                result[name] = value
        return result

    def overrides(self) -> dict[str, AnimationConfig]:
        result: dict[str, AnimationConfig] = {}
        selections = self.selections()
        for name in AnimationsTab.ANIMATIONS:
            if selections.get(name) == "off":
                continue
            base = self.base_config(name)
            current = self.current_config(name)
            if self.comparable(current) == self.comparable(base):
                continue
            result[name] = current
        return result

    def _validate_overrides(self, overrides: dict[str, AnimationConfig]) -> list[str]:
        """Set error text on defined inputs whose values are out of range."""
        invalid: list[str] = []
        for name in AnimationsTab.ANIMATIONS:
            config = overrides.get(name)
            fields = (
                ("duration_ms", self.duration_inputs[name], 0, False),
                ("damping_ratio", self.damping_inputs[name], 0, False),
                ("stiffness", self.stiffness_inputs[name], 0, False),
                ("epsilon", self.epsilon_inputs[name], 0, True),
            )
            bad = False
            for key, field, minimum, positive in fields:
                value = config.get(key) if config else None
                if not isinstance(value, (int, float)):
                    field.error = None
                    continue
                out_of_range = value <= minimum if positive else value < minimum
                field.error = (
                    f"Must be {'> 0' if positive else '>= 0'}" if out_of_range else None
                )
                bad = bad or out_of_range
            if bad:
                invalid.append(name)
        return invalid

    def build_override_children(self, config: AnimationConfig) -> list[kdl.Node] | None:
        if config["kind"] == "spring":
            if None in (
                config.get("damping_ratio"),
                config.get("stiffness"),
                config.get("epsilon"),
            ):
                return None
            return [
                kdl.Node(
                    name="spring",
                    props={
                        "damping-ratio": config["damping_ratio"],
                        "stiffness": config["stiffness"],
                        "epsilon": config["epsilon"],
                    },
                )
            ]

        nodes: list[kdl.Node] = []
        if config.get("duration_ms") is not None:
            nodes.append(kdl.Node(name="duration-ms", args=[config["duration_ms"]]))
        curve = config.get("curve")
        if curve:
            if curve == "cubic-bezier":
                bezier = cast(list[float] | None, config.get("bezier"))
                if not bezier or len(bezier) != 4:
                    return None
                nodes.append(kdl.Node(name="curve", args=["cubic-bezier", *bezier]))
            else:
                nodes.append(kdl.Node(name="curve", args=[curve]))
        if not nodes:
            return None
        return nodes

    def _override_children_lines(self, config: AnimationConfig) -> list[str] | None:
        children = self.build_override_children(config)
        if children is None:
            return None
        return [c.print().rstrip("\n") for c in children]

    def _filtered_body_lines(self, lines: list[str]) -> list[str]:
        kept: list[str] = []
        in_string = False
        raw_hashes = 0
        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]
            stripped = line.strip()
            if in_string:
                kept.append(line)
                if stripped.endswith('"' + "#" * raw_hashes):
                    in_string = False
                i += 1
                continue
            if (
                re.match(r"custom-shader\s", stripped)
                and ('r"' in stripped or "r#" in stripped)
                and stripped.count('"') % 2 == 1
            ):
                raw_hashes = self._raw_hash_count(stripped)
                in_string = True
                kept.append(line)
                i += 1
                continue
            if re.match(r"(?:duration-ms|curve|spring|off)(?:[ \t{]|$)", stripped):
                if "{" in stripped:
                    depth = stripped.count("{") - stripped.count("}")
                    i += 1
                    while i < n and depth > 0:
                        depth += lines[i].count("{") - lines[i].count("}")
                        i += 1
                    continue
                i += 1
                continue
            kept.append(line)
            i += 1
        return kept

    def _node_body_lines(self, text: str) -> list[str]:
        start = text.find("{")
        end = text.rfind("}")
        return text[start + 1 : end].splitlines()

    def override_animation_node_text(
        self, name: str, text: str, config: AnimationConfig
    ) -> str | None:
        lines = text.splitlines()
        if not lines:
            return None
        indent = "    "
        override = self._override_children_lines(config)
        if override is None:
            return None
        body = [f"{indent * 2}{line}" for line in override]
        body.extend(self._filtered_body_lines(self._node_body_lines(text)))
        return "\n".join([f"{indent}{name} {{", *body, f"{indent}}}"])

    def _indent_block(self, text: str, indent: str) -> str:
        lines = text.splitlines()
        if lines:
            lines[0] = lines[0].lstrip()
        return "\n".join(indent + line for line in lines)

    def _depth_lines(self, text: str) -> list[tuple[int, str]]:
        result: list[tuple[int, str]] = []
        depth = 0
        i = 0
        line_start = 0
        n = len(text)
        while i < n:
            ch = text[i]
            if ch == '"':
                i = self._skip_string(text, i)
                continue
            if ch == "/":
                j = self._skip_comment(text, i)
                if j is not None:
                    i = j
                    continue
            if ch in "\n\r":
                result.append((depth, text[line_start:i]))
                if ch == "\r" and i + 1 < n and text[i + 1] == "\n":
                    i += 1
                line_start = i + 1
                i += 1
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            i += 1
        if line_start < n:
            result.append((depth, text[line_start:]))
        return result

    def _raw_hash_count(self, line: str) -> int:
        m = re.search(r'r(#*)"', line)
        return len(m.group(1)) if m else 0

    def _strip_shader_block(self, lines: list[str]) -> list[str]:
        kept: list[str] = []
        in_string = False
        raw_hashes = 0
        for line in lines:
            stripped = line.strip()
            if in_string:
                if stripped.endswith('"' + "#" * raw_hashes):
                    in_string = False
                continue
            if (
                re.match(r"custom-shader\s", stripped)
                and ('r"' in stripped or "r#" in stripped)
                and stripped.count('"') % 2 == 1
            ):
                raw_hashes = self._raw_hash_count(stripped)
                in_string = True
                continue
            kept.append(line)
        return kept

    def _parse_node_values(self, name: str, body: list[str]) -> AnimationConfig | None:
        node_text = f"{name} {{\n" + "\n".join(self._strip_shader_block(body)) + "\n}"
        doc = kdl.parse(node_text)
        node = cast(list[KDLNode], doc.nodes)[0]
        return self.parse_animation_node(node)

    def read_animations_kdl(
        self,
    ) -> tuple[
        bool, float | None, dict[str, str | None], dict[str, AnimationConfig | None]
    ]:
        animations_off = False
        slowdown: float | None = None
        selections: dict[str, str | None] = {}
        overrides: dict[str, AnimationConfig | None] = {}
        self._parse_errors = set()

        path = os.path.join(NIRI_CONFIG_DIR, "animations.kdl")
        if os.path.exists(path):
            try:
                with open(path) as f:
                    text = f.read()
            except Exception:
                traceback.print_exc()
                text = ""
            if text:
                for depth, line in self._depth_lines(text):
                    if depth != 0:
                        continue
                    m = re.match(r'include\s+"([^"]+)"', line.strip())
                    if m:
                        for name in AnimationsTab.ANIMATIONS:
                            if f"/{name}/" in m.group(1):
                                selections[name] = m.group(1)

                block = self._find_node_text("animations", text, 0)
                if block is not None:
                    for depth, line in self._depth_lines(block):
                        if depth != 1:
                            continue
                        stripped = line.strip()
                        if stripped == "off":
                            animations_off = True
                        elif stripped.startswith("slowdown "):
                            m = re.match(r"slowdown\s+([0-9.]+)", stripped)
                            if m:
                                try:
                                    slowdown = float(m.group(1))
                                except ValueError:
                                    traceback.print_exc()
                        elif stripped.startswith("// preset: "):
                            preset = stripped[len("// preset: ") :].strip()
                            for name in AnimationsTab.ANIMATIONS:
                                if f"/{name}/" in preset:
                                    selections[name] = preset

                    for name in AnimationsTab.ANIMATIONS:
                        node_text = self._find_node_text(name, text, 1)
                        if node_text is None:
                            continue
                        body = self._node_body_lines(node_text)
                        if any(line.strip() == "off" for line in body):
                            selections[name] = "off"
                            continue
                        try:
                            overrides[name] = self._parse_node_values(name, body)
                        except Exception:
                            traceback.print_exc()
                            self._parse_errors.add(name)

        if slowdown is None:
            slowdown = self.read_config_slowdown()

        return animations_off, slowdown, selections, overrides

    def _report_parse_errors(self) -> bool:
        if not self._parse_errors:
            return False
        self.set_status(
            f"Unparseable nodes: {', '.join(sorted(self._parse_errors))}", "red"
        )
        return True

    def read_config_slowdown(self) -> float | None:
        path = os.path.join(NIRI_CONFIG_DIR, "config.kdl")
        if not os.path.exists(path):
            return None

        try:
            with open(path) as f:
                doc = kdl.parse(f.read())

        except Exception:
            traceback.print_exc()
            return None

        for node in cast(list[KDLNode], doc.nodes):
            if node.name != "animations":
                continue

            for child in node.nodes:
                if child.name == "slowdown" and child.args:
                    try:
                        return float(cast(int | float | str, child.args[0]))
                    except (TypeError, ValueError):
                        traceback.print_exc()
                        return None
        return None

    def write_animations_kdl(self) -> bool:
        selections = self.selections()
        overrides = self.overrides()
        invalid_ranges = self._validate_overrides(overrides)
        if invalid_ranges:
            self.set_status(
                f"Invalid values, not written: {', '.join(invalid_ranges)}", "red"
            )
            self.update()
            return False
        if self._parse_errors:
            self.set_status(
                "Unparseable nodes, not written: "
                + ", ".join(sorted(self._parse_errors)),
                "red",
            )
            self.update()
            return False
        indent = "    "

        lines: list[str] = ["animations {"]
        if self.animations_off:
            lines.append(f"{indent}off")
        lines.append(f"{indent}slowdown {round(self.slowdown_value, 2)}")

        invalid: list[str] = []
        for name in AnimationsTab.ANIMATIONS:
            choice = selections.get(name)
            if choice == "off":
                lines.append(f"{indent}{name} {{")
                lines.append(f"{indent}{indent}off")
                lines.append(f"{indent}}}")
                continue

            config = overrides.get(name)
            if choice not in (None, "off"):
                text = self.extract_animation_node_text(name, choice)
                if text is None:
                    invalid.append(name)
                    continue
                if config is not None:
                    node_text = self.override_animation_node_text(name, text, config)
                    if node_text is None:
                        invalid.append(name)
                        continue
                else:
                    node_text = self._indent_block(text, indent)
                lines.append(f"{indent}// preset: {choice}")
                lines.append(node_text)
                continue

            if config is not None:
                children = self._override_children_lines(config)
                if children is None:
                    invalid.append(name)
                    continue
                lines.append(f"{indent}{name} {{")
                for child in children:
                    lines.append(f"{indent}{indent}{child}")
                lines.append(f"{indent}}}")
        lines.append("}")

        content = "\n".join(lines) + "\n"

        if invalid:
            self.set_status(
                f"Incomplete override, not written: {', '.join(invalid)}", "red"
            )
            self.update()
            return False

        target = os.path.join(NIRI_CONFIG_DIR, "animations.kdl")
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if os.path.exists(target):
                with open(target, "rb") as src, open(f"{target}.bak", "wb") as dst:
                    _ = dst.write(src.read())

            fd, tmp = tempfile.mkstemp(
                dir=os.path.dirname(target), prefix=".animations.kdl.", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w") as f:
                    _ = f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
                if os.path.exists(target):
                    os.chmod(tmp, os.stat(target).st_mode)
                os.replace(tmp, target)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise

        except Exception as e:
            traceback.print_exc()
            self.set_status(f"Error writing KDL config: {e}", "red")
            self.update()
            return False

        return True

    def on_apply(self) -> None:
        if self.write_animations_kdl():
            self.set_status("Applied settings", "green")
            self.update()

    def on_reset(self) -> None:
        animations_off, slowdown, selections, overrides = self.read_animations_kdl()
        self.set_state(animations_off, slowdown, selections, overrides)
        if not self._report_parse_errors():
            self.set_status("All changes reset", "gray")
        self.update()

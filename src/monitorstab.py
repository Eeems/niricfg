# pyright: reportPrivateImportUsage=false
import json
import os
import subprocess
import tempfile
import traceback
from typing import cast

import flet as ft
import kdl

from monitor import Monitor
from settingspanel import SettingsPanel

CONFIG_PATH = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
    "niri",
    "monitors.kdl",
)

OutputData = dict[str, int | float | bool | str | list[dict[str, int]]]


@ft.control
class MonitorsTab(ft.Container):
    def __init__(self) -> None:
        self.selected_monitor_name: str | None = None
        self.primary_monitor_name: str | None = None
        self.canvas_width: float = 0.0
        self.canvas_height: float = 0.0
        self.canvas_scale_factor: float = 1.0
        self.canvas_min_x: int = 0
        self.canvas_min_y: int = 0
        self.outputs: dict[str, OutputData] = {}

        self.status_text: ft.Text = ft.Text("", size=14, color="gray")
        self.canvas: ft.Stack = ft.Stack(
            expand=True, on_size_change=self.on_canvas_resize
        )
        self.settings_panel: SettingsPanel = SettingsPanel(
            on_resolution_change=lambda _: self.update_display(),
            on_scale_change=lambda _: self.update_display(),
            on_vrr_change=lambda _: self.update_display(),
            on_make_primary_click=lambda _: self.on_make_primary_click(),
            on_x_change=lambda _: self.update_display(),
            on_y_change=lambda _: self.update_display(),
            on_apply=lambda m, e: self.on_apply(e),
            on_reset=self.on_reset,
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
                    ft.Row(
                        [
                            ft.Container(
                                content=self.canvas,
                                expand=True,
                                border=ft.Border.all(2, "gray"),
                                padding=5,
                            ),
                            self.settings_panel,
                        ],
                        expand=True,
                        spacing=10,
                    ),
                ],
                expand=True,
                spacing=10,
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
            self.settings_panel.apply()
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

    def set_status(self, message: str, color: str = "gray") -> None:
        self.status_text.value = message
        self.status_text.color = color
        self.status_text.update()

    def refresh(self) -> bool:
        try:
            result = subprocess.run(
                ["niri", "msg", "--json", "outputs"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )

            if result.returncode != 0:
                self.set_status(f"Error: niri returned {result.returncode}", "red")
                self.page.schedule_update()
                return False

            self.outputs = cast(dict[str, OutputData], json.loads(result.stdout))
            self.primary_monitor_name = self.get_primary_monitor()

            if not self.outputs:
                self.set_status("No monitors connected", "red")

            else:
                self.set_status("")

            self.update_canvas_display()
            if self.selected_monitor_name:
                self.select_monitor_by_name(self.selected_monitor_name)

            self.page.schedule_update()
            return True

        except Exception as e:
            traceback.print_exc()
            self.set_status(f"Error: {e}", "red")
            self.page.schedule_update()
            return False

    def update_display(self) -> None:
        self.update_status()
        self.update_canvas_display()

    def on_make_primary_click(self) -> None:
        if not self.selected_monitor_name:
            return

        if self.selected_monitor_name == self.primary_monitor_name:
            return

        self.primary_monitor_name = self.selected_monitor_name
        self.update_display()

    def update_status(self) -> None:
        if self.selected_monitor_name is not None:
            monitor = self.get_monitor(self.selected_monitor_name)
            if monitor is not None and monitor.pending:
                self.set_status("Pending changes", "orange")
                return

        self.set_status("")

    def on_canvas_resize(self, e: ft.LayoutSizeChangeEvent[ft.LayoutControl]) -> None:
        self.canvas_width = e.width
        self.canvas_height = e.height
        self.update_canvas_display()

    def calculate_scaling_factor(self) -> None:
        canvas_max_x: int = 0
        canvas_max_y: int = 0
        first = True
        for name, output in self.outputs.items():
            monitor = self.get_monitor(name)
            if monitor:
                x, y = monitor.position
                width, height = monitor.resolution
                width = int(width / monitor.monitor_scale)
                height = int(height / monitor.monitor_scale)

            else:
                logical = cast(
                    dict[str, int | float | bool], output.get("logical") or {}
                )
                x = cast(int, logical.get("x", 0))
                y = cast(int, logical.get("y", 0))
                width = cast(int, logical.get("width", 1920))
                height = cast(int, logical.get("height", 1080))

            if first:
                self.canvas_min_x = x
                self.canvas_min_y = y
                canvas_max_x = x + width
                canvas_max_y = y + height
                first = False
            else:
                self.canvas_min_x = min(x, self.canvas_min_x)
                self.canvas_min_y = min(y, self.canvas_min_y)
                canvas_max_x = max(x + width, canvas_max_x)
                canvas_max_y = max(y + height, canvas_max_y)

        self.canvas_scale_factor = (
            min(
                self.canvas_width / max(canvas_max_x - self.canvas_min_x, 1),
                self.canvas_height / max(canvas_max_y - self.canvas_min_y, 1),
            )
            * 0.95
        )

    def update_canvas_controls(self) -> None:
        for monitor in cast(list[Monitor], self.canvas.controls):
            try:
                monitor.update()

            except RuntimeError:
                pass

    def is_primary_monitor(self, monitor: Monitor) -> bool:
        return monitor.name == self.primary_monitor_name

    def is_selected_monitor(self, monitor: Monitor) -> bool:
        return monitor.name == self.selected_monitor_name

    def layout_monitor(self, monitor: Monitor) -> None:
        assert monitor.left is not None
        assert monitor.top is not None
        assert monitor.width is not None
        assert monitor.height is not None
        monitor.left = (monitor.left - self.canvas_min_x) * self.canvas_scale_factor
        monitor.top = (monitor.top - self.canvas_min_y) * self.canvas_scale_factor
        monitor.width *= self.canvas_scale_factor
        monitor.height *= self.canvas_scale_factor

    def update_canvas_display(self) -> None:
        """Update canvas without re-fetching from niri - just refreshes the display based on current data"""
        try:
            valid_outputs = list(self.outputs.keys())
            self.calculate_scaling_factor()
            for name, output in self.outputs.items():
                logical = cast(
                    dict[str, int | float | bool], output.get("logical") or {}
                )

                x = cast(int, logical.get("x", 0))
                y = cast(int, logical.get("y", 0))
                scale = cast(float, logical.get("scale", 1.0))
                modes = cast(list[dict[str, int]], output.get("modes") or [])
                current_mode = output.get("current_mode")
                if isinstance(current_mode, int) and 0 <= current_mode < len(modes):
                    mode = modes[current_mode]
                else:
                    mode = {}
                width = mode.get("width", 1920)
                height = mode.get("height", 1080)

                monitor = self.get_monitor(name)
                if monitor is None:
                    monitor = Monitor(
                        name=name,
                        resolution=(width, height),
                        position=(x, y),
                        scale=scale,
                        vrr=cast(bool, output.get("vrr_enabled", False)),
                        on_click=lambda _, n=name: self.select_monitor_by_name(n),
                        is_primary=self.is_primary_monitor,
                        is_selected=self.is_selected_monitor,
                        on_layout=self.layout_monitor,
                    )
                    self.canvas.controls.append(monitor)

                else:
                    if "scale" not in monitor.pending:
                        monitor.monitor_scale = scale

                    if "resolution" not in monitor.pending:
                        monitor.resolution = (width, height)

                    if "position" not in monitor.pending:
                        monitor.position = (x, y)

                    if "vrr" not in monitor.pending:
                        monitor.vrr = cast(bool, output.get("vrr_enabled", False))

            for monitor in cast(list[Monitor], list(self.canvas.controls)):
                if monitor.name not in valid_outputs:
                    if monitor.name == self.selected_monitor_name:
                        self.selected_monitor_name = None
                        self.settings_panel.monitor = None
                    self.canvas.controls.remove(monitor)

        except Exception as e:
            traceback.print_exc()
            self.set_status(f"Error: {e}", "red")

        finally:
            self.page.schedule_update()
            self.update_canvas_controls()

    def get_monitor(self, name: str) -> Monitor | None:
        for monitor in cast(list[Monitor], self.canvas.controls):
            if monitor.name == name:
                return monitor

        return None

    def select_monitor_by_name(self, name: str) -> None:
        output = self.outputs.get(name)
        if output:
            self.select_monitor(output)

    def select_monitor(self, output: OutputData) -> None:
        self.selected_monitor_name = cast(str | None, output.get("name"))
        if not self.selected_monitor_name:
            self.settings_panel.monitor = None
            self.update_canvas_controls()
            return

        monitor = self.get_monitor(self.selected_monitor_name)
        self.settings_panel.monitor = monitor
        self.update_canvas_controls()
        if not monitor:
            return

        try:
            # Get available modes and populate dropdown. Sort a copy so the
            # original modes list keeps its order for current_mode indexing.
            modes = sorted(
                cast(list[dict[str, int]], output.get("modes", [])),
                key=lambda m: (m["width"], m["height"]),
                reverse=True,
            )
            mode_options: list[ft.dropdown.Option] = []
            seen: set[str] = set()
            for mode in modes:
                mode_str = f"{mode['width']}x{mode['height']}"
                if mode_str not in seen:
                    seen.add(mode_str)
                    mode_options.append(ft.dropdown.Option(mode_str))
            self.settings_panel.resolution_dropdown.options = mode_options
            w, h = monitor.resolution
            self.settings_panel.resolution_dropdown.value = f"{w}x{h}"
            self.settings_panel.scale_slider.value = monitor.monitor_scale
            self.settings_panel.scale_input.value = str(monitor.monitor_scale)
            self.settings_panel.vrr_switch.value = monitor.vrr
            x, y = monitor.position
            self.settings_panel.pos_x_input.value = str(x)
            self.settings_panel.pos_y_input.value = str(y)
            self.settings_panel.primary_button.disabled = monitor.primary
            self.settings_panel.update()
            monitor.update()
            self.update_display()
        except Exception as e:
            traceback.print_exc()
            self.set_status(f"Error: {e}", "red")
            self.page.schedule_update()

    def get_primary_monitor(self) -> str | None:
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH) as f:
                    doc = kdl.parse(f.read())
                    for node in doc.nodes:
                        if node.name == "output" and node.args:
                            name = str(cast(object, node.args[0]))
                            for child in node.nodes:
                                if child.name == "focus-at-startup":
                                    return name
        except Exception:
            traceback.print_exc()

        return None

    def write_kdl_config(self) -> bool:
        """Write monitor configuration to ~/.config/niri/monitors.kdl"""
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

            try:
                with open(CONFIG_PATH) as f:
                    kdl_config = kdl.parse(f.read())
            except FileNotFoundError:
                kdl_config = kdl.Document()
            except Exception:
                traceback.print_exc()
                raise

            managed = (
                "mode",
                "scale",
                "position",
                "variable-refresh-rate",
                "focus-at-startup",
            )
            outputs: dict[str, kdl.Node] = {}
            for node in kdl_config.nodes:
                if node.name == "output" and node.args:
                    outputs[cast(str, node.args[0])] = node

            for monitor in sorted(
                cast(list[Monitor], self.canvas.controls), key=lambda x: x.name
            ):
                node = outputs.get(monitor.name)
                if node is None:
                    node = kdl.Node(name="output", args=[monitor.name])
                    kdl_config.nodes.append(node)

                node.nodes = [c for c in node.nodes if c.name not in managed]

                w, h = monitor.resolution
                x, y = monitor.position
                nodes = [
                    kdl.Node(name="mode", args=[f"{w}x{h}"]),
                    kdl.Node(name="scale", args=[monitor.monitor_scale]),
                    kdl.Node(
                        name="position",
                        args=[],
                        props={"x": x, "y": y},
                    ),
                ]
                if monitor.vrr:
                    nodes.append(kdl.Node(name="variable-refresh-rate"))
                if monitor.primary:
                    nodes.append(kdl.Node(name="focus-at-startup"))
                node.nodes.extend(nodes)

            fd, tmp = tempfile.mkstemp(
                dir=os.path.dirname(CONFIG_PATH),
                prefix=".monitors.kdl.",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w") as f:
                    _ = f.write(kdl_config.print())
                os.replace(tmp, CONFIG_PATH)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise

            return True

        except Exception as e:
            traceback.print_exc()
            self.set_status(f"Error writing KDL config: {e}", "red")
            self.page.schedule_update()
            return False

    def on_apply(self, errors: list[str]) -> None:
        if errors:
            self.set_status(f"Errors: {'; '.join(errors)}", "red")
            return

        if not self.write_kdl_config():
            return

        if self.refresh():
            self.set_status("Applied settings", "green")

    def on_reset(self, monitor: Monitor | None = None) -> None:
        if monitor is None:
            monitor = self.get_monitor(self.selected_monitor_name or "")
        if monitor is None:
            return
        if "primary" in monitor.pending:
            self.primary_monitor_name = self.get_primary_monitor()
        monitor.reset()
        self.set_status("All changes reset", "gray")
        self.update_canvas_display()

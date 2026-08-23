import flet as ft

from animationstab import AnimationsTab
from monitorstab import MonitorsTab


def main(page: ft.Page) -> None:
    page.title = "Niri Monitor Configuration"

    def on_close() -> None:
        nonlocal closed
        closed = True

    page.on_close = lambda _: on_close()

    closed: bool = False

    monitors_tab = MonitorsTab()
    animations_tab = AnimationsTab()

    def on_tab_change(e: ft.Event[ft.Tabs]) -> None:
        if int(e.data or 0) == 0:
            monitors_tab.focus_keyboard()
        else:
            animations_tab.focus_keyboard()

    page.on_resize = lambda _: animations_tab.relayout()
    page.add(
        ft.Tabs(
            length=2,
            expand=True,
            on_change=on_tab_change,
            content=ft.Column(
                expand=True,
                controls=[
                    ft.TabBar(
                        tabs=[
                            ft.Tab(label="Monitors"),
                            ft.Tab(label="Animations"),
                        ],
                    ),
                    ft.TabBarView(
                        expand=True,
                        controls=[
                            monitors_tab,
                            animations_tab,
                        ],
                    ),
                ],
            ),
        )
    )
    _ = monitors_tab.refresh()
    animations_tab.refresh()
    monitors_tab.focus_keyboard()


if __name__ == "__main__":
    _ = ft.run(main)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

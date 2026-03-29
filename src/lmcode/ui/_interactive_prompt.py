from __future__ import annotations

from typing import Any

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.widgets import TextArea


def display_interactive_approval(tool_name: str, path_or_cmd: str) -> str | None:
    """Show an inline interactive approval menu for tools in 'ask' mode.
    Returns:
      "yes": user approved
      "no": user denied
      "always": user approved and wants to auto-allow this tool
      "<string>": user typed a redirect instruction
      None: user pressed Ctrl+C
    """
    options = [
        ("yes", "Yes"),
        ("no", "No"),
        ("always", "Yes — and allow this tool automatically from now on"),
    ]
    selected_index = 0

    text_area = TextArea(
        prompt="[Text input box] ...or tell lmcode what to do instead: ", multiline=False
    )

    def get_radio_text() -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        result.append(("", f"Allow this change? ({tool_name})\n"))
        for i, (_val, label) in enumerate(options):
            if i == selected_index:
                result.append(("class:selected", f"❯ {label}\n"))
            else:
                result.append(("", f"  {label}\n"))
        return result

    radio_window = Window(content=FormattedTextControl(get_radio_text), dont_extend_height=True)

    root_container = HSplit([radio_window, text_area])

    layout = Layout(root_container, focused_element=text_area)

    kb = KeyBindings()

    @kb.add("up")
    def _up(event: Any) -> None:
        nonlocal selected_index
        selected_index = max(0, selected_index - 1)

    @kb.add("down")
    def _down(event: Any) -> None:
        nonlocal selected_index
        selected_index = min(len(options) - 1, selected_index + 1)

    @kb.add("enter")
    def _enter(event: Any) -> None:
        if text_area.text.strip():
            event.app.exit(result=text_area.text)
        else:
            event.app.exit(result=options[selected_index][0])

    # Keyboard interrupt handler
    @kb.add("c-c")
    def _ctrl_c(event: Any) -> None:
        event.app.exit(result=None)

    app: Application[str | None] = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
    )

    return app.run()

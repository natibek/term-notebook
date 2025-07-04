from textual.reactive import reactive
from textual.app import ComposeResult
from textual.widgets import Button, Rule, Label, TextArea
from textual.containers import HorizontalGroup, VerticalScroll, Container
from textual.events import Key, DescendantFocus

from typing import Any
import os.path
import json

from markdown_cell import MarkdownCell, FocusMarkdown
from code_cell import CodeCell, CodeArea
from notebook_kernel import NotebookKernel
from save_as_screen import SaveAsScreen


class ButtonRow(HorizontalGroup):
    def compose(self) -> ComposeResult:
        yield Button("➕ Code", id="add-code-cell")
        yield Button("➕ Markdown", id="add-markdown-cell")
        yield Button("▶ Run All", id="run-all")
        yield Button("🔁 Restart", id="restart-shell")


class Notebook(Container):
    """A Textual app to manage stopwatches."""

    valid_notebook = reactive(True)

    _last_click_time: float = 0.0
    last_focused = None
    SCREENS = {"save_as_screen": SaveAsScreen}
    BINDINGS = [
        ("a", "add_cell_after", "Add cell after"),
        ("b", "add_cell_before", "Add cell before"),
        ("ctrl+d", "delete_cell", "Delete cell"),
        ("ctrl+s", "save", "Save"),
        ("ctrl+w", "save_as", "Save As"),
    ]

    def __init__(self, path: str, id: str) -> None:
        super().__init__(id=id)

        self.path = path
        self.notebook_kernel = NotebookKernel()

        self._metadata: dict[str, Any] | None = None
        self._nbformat: int = 4
        self._nbformat_minor: int = 5

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield ButtonRow()
        yield Rule(line_style="double", id="header-rule")
        self.cell_container = VerticalScroll(id="cell-container")
        yield self.cell_container

        yield Label(
            f"{self.path} is not a valid notebook. "
            "File does not have a .ipynb extension."
        )

    def on_mount(self):
        self.load_notebook()
        self.call_after_refresh(self.cell_container.focus)

    def on_unmount(self) -> None:
        if self.notebook_kernel:
            self.notebook_kernel.shutdown_kernel()

    def on_descendant_focus(self, event: DescendantFocus) -> None:
        # Ignore buttons
        if isinstance(event.widget, CodeCell) or isinstance(event.widget, MarkdownCell):
            self.last_focused = event.widget
        elif any(
            isinstance(event.widget, widgetType)
            for widgetType in [CodeArea, FocusMarkdown, TextArea]
        ):
            self.last_focused = event.widget.parent.parent

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "add-code-cell":
                widget = await self.add_cell(CodeCell, "after")
                self.call_after_refresh(widget.open)
            case "add-markdown-cell":
                widget = await self.add_cell(MarkdownCell, "after")
                self.call_after_refresh(widget.open)
            case "restart-shell":
                self.notebook_kernel.restart_kernel()
            case "run-all":
                for child in self.cell_container.children:
                    if isinstance(child, CodeCell):
                        await child.run_cell()

    async def action_add_cell_after(self) -> None:
        await self.add_cell(CodeCell, "after")

    async def action_add_cell_before(self) -> None:
        await self.add_cell(CodeCell, "before")

    def action_save_as(self) -> None:
        self.app.switch_screen("save_as_screen")

    def action_save(self) -> None:
        if self.path == "new_empty_terminal_notebook":
            self.action_save_as()
        else:
            nb = self.to_nb()
            with open(self.path, "w") as nb_file:
                json.dump(nb, nb_file)

    def action_delete_cell(self) -> None:
        # TODO: Move to cells
        # TODO: Change the focused cell when one is deleted
        if self.last_focused:
            self.last_focused.remove()
            self.last_focused = None

    def watch_valid_notebook(self, is_valid: bool) -> None:
        for node in [ButtonRow, Rule, VerticalScroll]:
            self.query_one(node).display = is_valid

        self.query_one(Label).display = not is_valid

    def focus(self):
        if self.last_child:
            self.call_after_refresh(self.last_child.focus)
        else:
            self.call_after_refresh(self.cell_container.focus)

    def load_notebook(self):
        if self.path == "new_empty_terminal_notebook":
            return

        if not os.path.exists(self.path):
            self.valid_notebook = False
            return

        if os.path.splitext(self.path)[1] != ".ipynb":
            self.valid_notebook = False
            return

        with open(self.path, "r") as notebook_file:
            content = json.load(notebook_file)
            for cell in content["cells"]:
                if cell["cell_type"] == "code":
                    code_cell = CodeCell.from_nb(cell, self)
                    self.cell_container.mount(code_cell)
                elif cell["cell_type"] == "markdown":
                    markdown_cell = MarkdownCell.from_nb(cell)
                    self.cell_container.mount(markdown_cell)

    async def add_cell(
        self, cell_type, position: str = "after", **cell_kwargs
    ) -> CodeCell | MarkdownCell:
        """
        Position is after or before.
        """
        kwargs = {position: self.last_focused}

        if cell_type is CodeCell:
            cell_kwargs["notebook"] = self

        widget = cell_type(**cell_kwargs)
        await self.cell_container.mount(widget, **kwargs)

        if not self.last_focused:
            self.last_focused = widget
            self.last_focused.focus()
        return widget

    def to_nb(self) -> dict[str, Any]:
        """
        Format for notebook
        {
            "metadata" : {
                "signature": "hex-digest",
                "kernel_info": {
                    "name" : "the name of the kernel"
                },
                "language_info": {
                    "name" : "the programming language of the kernel",
                    "version": "the version of the language",
                    "codemirror_mode": "The name of the codemirror mode to use [optional]"
                }
            },
            "nbformat": 4,
            "nbformat_minor": 0,
            "cells" : [
            ],
        }
        """
        kernel_spec = self.notebook_kernel.get_kernel_spec()
        kernel_info = self.notebook_kernel.get_kernel_info()
        language_info = self.notebook_kernel.get_language_info()

        cells = [cell.to_nb() for cell in self.cell_container.children]

        return {
            "metadata": {
                "kernel_info": kernel_info,
                "kernel_spec": kernel_spec,
                "language_info": language_info,
            },
            "nbformat": self._nbformat,
            "nbformat_minor": self._nbformat_minor,
            "cells": cells,
        }

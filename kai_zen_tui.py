import io
import os
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, RichLog, Static

from kai_zen_cli import HARDWARE_PROFILE, KaiZenCLI, LOGO_PATH, MODEL_CATALOG, SESSIONS_DIR, now_stamp


COMMAND_CATALOG = [
    {"name": "/download", "label": "Download model", "description": "Open the searchable model browser", "query_hint": "qwen"},
    {"name": "/model", "label": "Switch model", "description": "Pick an installed model with arrows"},
    {"name": "/load", "label": "Load session", "description": "Browse saved sessions and restore one"},
    {"name": "/settings", "label": "View settings", "description": "Inspect the active runtime config"},
    {"name": "/help", "label": "Command help", "description": "See every available slash command"},
    {"name": "/new", "label": "New session", "description": "Start a fresh conversation"},
    {"name": "/clearimage", "label": "Clear images", "description": "Drop queued image attachments"},
]


class DownloadScreen(ModalScreen[dict | None]):
    CSS = """
    DownloadScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.78);
    }

    #download-shell {
        width: 92;
        height: 32;
        border: round #4a4259;
        background: #0a0a0d;
        padding: 1 2;
    }

    #download-title {
        color: #c6b3ff;
        text-style: bold;
        margin-bottom: 1;
    }

    #download-search {
        margin-bottom: 1;
    }

    #download-list {
        height: 1fr;
        border: round #2b2b33;
        margin-bottom: 1;
    }

    #download-meta {
        height: 6;
        border: round #4a4259;
        padding: 0 1;
    }
    """

    def __init__(self, backend: KaiZenCLI, initial_query: str = "") -> None:
        super().__init__()
        self.backend = backend
        self.initial_query = initial_query
        self.filtered = MODEL_CATALOG[:]
        self.installed = set()

    def compose(self) -> ComposeResult:
        with Container(id="download-shell"):
            yield Static("Kai-zen Model Download", id="download-title")
            yield Input(value=self.initial_query, placeholder="Search models", id="download-search")
            yield ListView(id="download-list")
            yield Static(id="download-meta")

    def on_mount(self) -> None:
        self.installed = self.backend.installed_models()
        self.refresh_models(self.initial_query)
        self.query_one("#download-search", Input).focus()

    def build_item(self, model: dict) -> ListItem:
        installed = model["name"] in self.installed
        guardrail = self.backend.model_guardrail(model)
        installed_text = "installed" if installed else guardrail["label"]
        line = Text()
        line.append(model["label"], style="bold #e4e4ea")
        line.append(f"  [{model['name']}]  ", style="#8e8e99")
        line.append(model["size"], style="#c6b3ff")
        line.append("  ")
        if installed:
            badge_style = "#b79cff"
        elif guardrail["level"] == "fit":
            badge_style = "#75c98b"
        elif guardrail["level"] == "stretch":
            badge_style = "#e5b567"
        elif guardrail["level"] == "heavy":
            badge_style = "#ff8f8f"
        else:
            badge_style = "#6f7685"
        line.append(installed_text, style=badge_style)
        item = ListItem(Label(line))
        item.model = model  # type: ignore[attr-defined]
        return item

    def refresh_models(self, query: str) -> None:
        self.filtered = self.backend.filter_model_catalog(query)
        list_view = self.query_one("#download-list", ListView)
        list_view.clear()
        if not self.filtered:
            self.query_one("#download-meta", Static).update("No models match your search.")
            return
        for model in self.filtered:
            list_view.append(self.build_item(model))
        list_view.index = 0
        self.update_meta(self.filtered[0])

    def update_meta(self, model: dict) -> None:
        tags = ", ".join(model["tags"])
        guardrail = self.backend.model_guardrail(model)
        text = Text()
        text.append(f"{model['label']}\n", style="bold #e4e4ea")
        text.append(f"modality: {model['modality']}    ", style="#b79cff")
        text.append(f"vram: {model['vram']}    ", style="#bcbcc7")
        text.append(f"speed: {model['speed']}\n", style="#c6b3ff")
        text.append(f"fit: {guardrail['label']}    ", style="#e5b567" if guardrail["level"] != "fit" else "#75c98b")
        text.append(f"target: {HARDWARE_PROFILE['gpu']}\n", style="#8e8e99")
        text.append(f"tags: {tags}\n", style="#8e8e99")
        text.append(guardrail["message"], style="#8e8e99")
        self.query_one("#download-meta", Static).update(text)

    def current_model(self) -> dict | None:
        list_view = self.query_one("#download-list", ListView)
        if not self.filtered or list_view.index is None:
            return None
        index = max(0, min(list_view.index, len(self.filtered) - 1))
        return self.filtered[index]

    @on(Input.Submitted, "#download-search")
    def submit_search(self) -> None:
        model = self.current_model()
        if model is not None:
            self.dismiss(model)

    def key_down(self) -> None:
        if not self.filtered:
            return
        list_view = self.query_one("#download-list", ListView)
        list_view.focus()
        list_view.index = min((list_view.index or 0) + 1, len(self.filtered) - 1)

    def key_up(self) -> None:
        if not self.filtered:
            return
        list_view = self.query_one("#download-list", ListView)
        list_view.focus()
        list_view.index = max((list_view.index or 0) - 1, 0)

    @on(Input.Changed, "#download-search")
    def update_search(self, event: Input.Changed) -> None:
        self.refresh_models(event.value)

    @on(ListView.Highlighted, "#download-list")
    def on_highlight(self, event: ListView.Highlighted) -> None:
        if event.item is not None:
            self.update_meta(event.item.model)  # type: ignore[attr-defined]

    @on(ListView.Selected, "#download-list")
    def on_select(self, event: ListView.Selected) -> None:
        if event.item is not None:
            self.dismiss(event.item.model)  # type: ignore[attr-defined]

    def key_escape(self) -> None:
        self.dismiss(None)


class CommandScreen(ModalScreen[dict | None]):
    CSS = DownloadScreen.CSS.replace("DownloadScreen", "CommandScreen")

    def __init__(self, initial_query: str = "") -> None:
        super().__init__()
        self.initial_query = initial_query
        self.filtered = COMMAND_CATALOG[:]

    def compose(self) -> ComposeResult:
        with Container(id="download-shell"):
            yield Static("Kai-zen Command Palette", id="download-title")
            yield Input(value=self.initial_query, placeholder="Search commands", id="download-search")
            yield ListView(id="download-list")
            yield Static(id="download-meta")

    def on_mount(self) -> None:
        self.refresh_commands(self.initial_query)
        self.query_one("#download-search", Input).focus()

    def refresh_commands(self, query: str) -> None:
        query = query.strip().lower().lstrip("/")
        self.filtered = [item for item in COMMAND_CATALOG if query in item["name"].lower() or query in item["label"].lower()]
        list_view = self.query_one("#download-list", ListView)
        list_view.clear()
        if not self.filtered:
            self.query_one("#download-meta", Static).update("No commands match. Try /download, /model, /load, or /settings.")
            return
        for item in self.filtered:
            line = Text()
            line.append(item["name"], style="bold #c6b3ff")
            line.append("  ")
            line.append(item["label"], style="#e4e4ea")
            row = ListItem(Label(line))
            row.command_item = item  # type: ignore[attr-defined]
            list_view.append(row)
        list_view.index = 0
        self.update_meta(self.filtered[0])

    def update_meta(self, item: dict) -> None:
        text = Text()
        text.append(f"{item['name']}\n", style="bold #e4e4ea")
        text.append(item["description"], style="#d7d7df")
        if item.get("query_hint"):
            text.append(f"\nTip: press Enter to open with search '{item['query_hint']}'.", style="#8e8e99")
        self.query_one("#download-meta", Static).update(text)

    @on(Input.Changed, "#download-search")
    def update_search(self, event: Input.Changed) -> None:
        self.refresh_commands(event.value)

    @on(Input.Submitted, "#download-search")
    def submit_search(self) -> None:
        if self.filtered:
            self.dismiss(self.filtered[0])

    @on(ListView.Highlighted, "#download-list")
    def on_highlight(self, event: ListView.Highlighted) -> None:
        if event.item is not None:
            self.update_meta(event.item.command_item)  # type: ignore[attr-defined]

    @on(ListView.Selected, "#download-list")
    def on_select(self, event: ListView.Selected) -> None:
        if event.item is not None:
            self.dismiss(event.item.command_item)  # type: ignore[attr-defined]

    def key_down(self) -> None:
        if not self.filtered:
            return
        list_view = self.query_one("#download-list", ListView)
        list_view.focus()
        list_view.index = min((list_view.index or 0) + 1, len(self.filtered) - 1)

    def key_up(self) -> None:
        if not self.filtered:
            return
        list_view = self.query_one("#download-list", ListView)
        list_view.focus()
        list_view.index = max((list_view.index or 0) - 1, 0)

    def key_escape(self) -> None:
        self.dismiss(None)


class SessionScreen(ModalScreen[str | None]):
    CSS = DownloadScreen.CSS.replace("DownloadScreen", "SessionScreen")

    def __init__(self, initial_query: str = "") -> None:
        super().__init__()
        self.initial_query = initial_query
        self.filtered: list[Path] = []

    def compose(self) -> ComposeResult:
        with Container(id="download-shell"):
            yield Static("Kai-zen Sessions", id="download-title")
            yield Input(value=self.initial_query, placeholder="Search sessions", id="download-search")
            yield ListView(id="download-list")
            yield Static(id="download-meta")

    def on_mount(self) -> None:
        self.refresh_sessions(self.initial_query)
        self.query_one("#download-search", Input).focus()

    def refresh_sessions(self, query: str) -> None:
        query = query.strip().lower()
        sessions = sorted(SESSIONS_DIR.glob("*.json"))
        self.filtered = [item for item in sessions if not query or query in item.stem.lower()]
        list_view = self.query_one("#download-list", ListView)
        list_view.clear()
        if not self.filtered:
            self.query_one("#download-meta", Static).update("No saved sessions found.")
            return
        for session in self.filtered:
            line = Text(session.stem, style="bold #e4e4ea")
            row = ListItem(Label(line))
            row.session_name = session.stem  # type: ignore[attr-defined]
            list_view.append(row)
        list_view.index = 0
        self.query_one("#download-meta", Static).update("Use arrows to choose a saved session, then press Enter.")

    @on(Input.Changed, "#download-search")
    def update_search(self, event: Input.Changed) -> None:
        self.refresh_sessions(event.value)

    @on(Input.Submitted, "#download-search")
    def submit_search(self) -> None:
        if self.filtered:
            self.dismiss(self.filtered[0].stem)

    @on(ListView.Selected, "#download-list")
    def on_select(self, event: ListView.Selected) -> None:
        if event.item is not None:
            self.dismiss(event.item.session_name)  # type: ignore[attr-defined]

    def key_down(self) -> None:
        if not self.filtered:
            return
        list_view = self.query_one("#download-list", ListView)
        list_view.focus()
        list_view.index = min((list_view.index or 0) + 1, len(self.filtered) - 1)

    def key_up(self) -> None:
        if not self.filtered:
            return
        list_view = self.query_one("#download-list", ListView)
        list_view.focus()
        list_view.index = max((list_view.index or 0) - 1, 0)

    def key_escape(self) -> None:
        self.dismiss(None)


class ModelScreen(ModalScreen[str | None]):
    CSS = DownloadScreen.CSS.replace("DownloadScreen", "ModelScreen")

    def __init__(self, backend: KaiZenCLI, initial_query: str = "") -> None:
        super().__init__()
        self.backend = backend
        self.initial_query = initial_query
        self.filtered: list[str] = []

    def compose(self) -> ComposeResult:
        with Container(id="download-shell"):
            yield Static("Kai-zen Installed Models", id="download-title")
            yield Input(value=self.initial_query, placeholder="Search installed models", id="download-search")
            yield ListView(id="download-list")
            yield Static(id="download-meta")

    def on_mount(self) -> None:
        self.refresh_models(self.initial_query)
        self.query_one("#download-search", Input).focus()

    def refresh_models(self, query: str) -> None:
        query = query.strip().lower()
        installed = sorted(self.backend.installed_models())
        self.filtered = [name for name in installed if not query or query in name.lower()]
        list_view = self.query_one("#download-list", ListView)
        list_view.clear()
        if not self.filtered:
            self.query_one("#download-meta", Static).update("No installed models found. Use /download to pull one first.")
            return
        for name in self.filtered:
            line = Text(name, style="bold #e4e4ea")
            row = ListItem(Label(line))
            row.model_name = name  # type: ignore[attr-defined]
            list_view.append(row)
        list_view.index = 0
        self.query_one("#download-meta", Static).update("Pick an installed model to make it active.")

    @on(Input.Changed, "#download-search")
    def update_search(self, event: Input.Changed) -> None:
        self.refresh_models(event.value)

    @on(Input.Submitted, "#download-search")
    def submit_search(self) -> None:
        if self.filtered:
            self.dismiss(self.filtered[0])

    @on(ListView.Selected, "#download-list")
    def on_select(self, event: ListView.Selected) -> None:
        if event.item is not None:
            self.dismiss(event.item.model_name)  # type: ignore[attr-defined]

    def key_down(self) -> None:
        if not self.filtered:
            return
        list_view = self.query_one("#download-list", ListView)
        list_view.focus()
        list_view.index = min((list_view.index or 0) + 1, len(self.filtered) - 1)

    def key_up(self) -> None:
        if not self.filtered:
            return
        list_view = self.query_one("#download-list", ListView)
        list_view.focus()
        list_view.index = max((list_view.index or 0) - 1, 0)

    def key_escape(self) -> None:
        self.dismiss(None)


class ConfirmScreen(ModalScreen[bool]):
    CSS = """
    ConfirmScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.78);
    }

    #confirm-shell {
        width: 78;
        height: auto;
        border: round #7a4b4b;
        background: #09090c;
        padding: 1 2;
    }

    #confirm-title {
        color: #ffb27c;
        text-style: bold;
        margin-bottom: 1;
    }
    """

    def __init__(self, title: str, message: str) -> None:
        super().__init__()
        self.title = title
        self.message = message

    def compose(self) -> ComposeResult:
        with Container(id="confirm-shell"):
            yield Static(self.title, id="confirm-title")
            yield Static(self.message)

    def key_enter(self) -> None:
        self.dismiss(True)

    def key_y(self) -> None:
        self.dismiss(True)

    def key_n(self) -> None:
        self.dismiss(False)

    def key_escape(self) -> None:
        self.dismiss(False)


class KaiZenTUI(App):
    CSS = """
    Screen {
        background: #000000;
        color: #e4e4ea;
    }

    #shell {
        layout: vertical;
    }

    #hero {
        height: auto;
        border: round #2b2b33;
        background: #09090c;
        padding: 1 2;
        margin: 1 1 0 1;
    }

    #body {
        height: 1fr;
        margin: 1;
    }

    #chat-log {
        width: 1fr;
        border: round #2b2b33;
        background: #09090c;
        padding: 0 1;
    }

    #side-panel {
        width: 32;
        border: round #4a4259;
        background: #09090c;
        padding: 0 1;
        margin-left: 1;
    }

    #composer {
        height: 5;
        border: round #4a4259;
        background: #09090c;
        padding: 0 1;
        margin: 1;
    }

    #command-hint {
        color: #888893;
        margin-top: 1;
    }

    #input {
        width: 1fr;
    }
    """

    BINDINGS = [("ctrl+c", "quit", "Quit"), ("ctrl+d", "quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self.backend = KaiZenCLI()
        self.compact_header = False

    def compose(self) -> ComposeResult:
        with Vertical(id="shell"):
            yield Static(id="hero")
            with Horizontal(id="body"):
                yield RichLog(id="chat-log", markup=True, wrap=True, highlight=True)
                yield Static(id="side-panel")
            with Container(id="composer"):
                yield Input(placeholder="Message Kai-zen or type / for the command palette", id="input")
                yield Static("Enter sends. Type / to open commands. /download, /model, and /load now open pickers with arrow-key navigation.", id="command-hint")
            yield Footer()

    def on_mount(self) -> None:
        self.compact_header = bool(self.backend.messages)
        self.update_hero()
        self.update_status()
        self.update_side_panel()
        self.post_system("Kai-zen TUI ready. Type `/` for the command palette. `/download` supports search, arrows, and guarded larger-model pulls.")
        self.query_one("#input", Input).focus()

    def update_hero(self) -> None:
        logo = self.load_logo_preview()
        title = Text()
        title.append("KAI-ZEN", style="bold #e4e4ea")
        title.append("  ", style="#8e8e99")
        title.append("TUI", style="bold #b79cff")
        subtitle = Text("Local model console for chat, downloads, sessions, and multimodal testing", style="#8e8e99")
        body = Text()
        body.append("Model ", style="#6f7685")
        body.append(self.backend.config["model"], style="bold #e4e4ea")
        body.append("   Backend ", style="#6f7685")
        body.append(self.backend.config["backend"], style="bold #b79cff")
        body.append("   Session ", style="#6f7685")
        body.append(self.backend.session_name, style="bold #bcbcc7")
        body.append("   Images ", style="#6f7685")
        body.append(str(len(self.backend.pending_images)), style="bold #b79cff")

        info = Text()
        info.append_text(title)
        if not self.compact_header:
            info.append("\n")
            info.append_text(subtitle)
            info.append("\n\n")
        else:
            info.append("\n")
        info.append_text(body)

        grid = Table.grid(expand=True, padding=(0, 2))
        grid.add_column(width=32 if not self.compact_header else 22)
        grid.add_column(ratio=1)
        logo_renderable = logo if logo is not None else Text("KZ", style="bold #b79cff")
        grid.add_row(logo_renderable, info)

        panel = Panel(grid, border_style="#2b2b33")
        self.query_one("#hero", Static).update(panel)

    def load_logo_preview(self) -> Text | None:
        if not LOGO_PATH.exists():
            return None
        color_term = os.environ.get("COLORTERM", "").lower()
        term = os.environ.get("TERM", "").lower()
        if color_term in {"truecolor", "24bit"}:
            chafa_colors = "full"
            converter_color = True
        elif os.name == "nt" and os.environ.get("WT_SESSION"):
            chafa_colors = "full"
            converter_color = True
        elif "256color" in term or color_term:
            chafa_colors = "256"
            converter_color = True
        else:
            chafa_colors = "none"
            converter_color = False
        for binary_name, command in (
            (
                "chafa",
                ["--symbols", "vhalf+braille", "--size", "30x10", "--colors", chafa_colors]
                if chafa_colors != "none"
                else ["--symbols", "ascii", "--size", "26x8", "--colors", "none"],
            ),
            ("ascii-image-converter", ["-C", "-b", "-W", "30"] if converter_color else ["-c", "-W", "26"]),
        ):
            binary = shutil.which(binary_name)
            if not binary:
                continue
            try:
                result = subprocess.run(
                    [binary, str(LOGO_PATH), *command],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                    check=True,
                )
            except Exception:
                continue
            rendered = result.stdout.strip("\n")
            if rendered.strip():
                try:
                    return Text.from_ansi(rendered)
                except Exception:
                    plain_lines = [line.rstrip() for line in rendered.splitlines() if line.strip()]
                    if plain_lines:
                        return Text("\n".join(plain_lines[:10]), style="#8e8e99")
        return None

    def update_status(self) -> None:
        self.update_hero()

    def update_side_panel(self) -> None:
        installed = sorted(self.backend.installed_models())
        installed_text = "\n".join(f"- {name}" for name in installed[:8]) or "- none"
        panel = Text()
        panel.append("Quick Actions\n", style="bold #b79cff")
        panel.append("/\n/download qwen\n/model\n/load\n/settings\n", style="#8e8e99")
        panel.append("\nInstalled\n", style="bold #e4e4ea")
        panel.append(installed_text, style="#8e8e99")
        self.query_one("#side-panel", Static).update(panel)

    def post_system(self, message: str) -> None:
        log = self.query_one("#chat-log", RichLog)
        log.write(Panel(Text(message, style="#d7d7df"), title="System", border_style="#3a3a46"))

    def post_user(self, message: str) -> None:
        log = self.query_one("#chat-log", RichLog)
        self.compact_header = True
        log.write(Panel(Text(message, style="#f0f0f4"), title="You", border_style="#5a4b78"))
        self.update_hero()

    def post_assistant(self, message: str) -> None:
        log = self.query_one("#chat-log", RichLog)
        log.write(Panel(Text(message, style="#d7d7df"), title=self.backend.config["model"], border_style="#7a68a2"))

    def post_output(self, title: str, output: str) -> None:
        log = self.query_one("#chat-log", RichLog)
        log.write(Panel(Text(output.rstrip() or "(no output)", style="#d7d7df"), title=title, border_style="#3a3a46"))

    def render_loaded_messages(self) -> None:
        log = self.query_one("#chat-log", RichLog)
        for message in self.backend.messages:
            role = message.get("role")
            content = str(message.get("content", "")).strip()
            if not content or role == "system":
                continue
            if role == "user":
                log.write(Panel(Text(content, style="#f0f0f4"), title="You", border_style="#5a4b78"))
            elif role == "assistant":
                log.write(Panel(Text(content, style="#d7d7df"), title=self.backend.config["model"], border_style="#7a68a2"))

    def capture_backend_output(self, fn) -> str:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            fn()
        return buffer.getvalue().strip()

    async def open_command_palette(self, initial_query: str = "") -> None:
        choice = await self.push_screen_wait(CommandScreen(initial_query))
        if not choice:
            return
        command = choice["name"]
        if command == "/download":
            await self.open_download(choice.get("query_hint", ""))
            return
        if command == "/model":
            await self.open_model_picker()
            return
        if command == "/load":
            await self.open_session_picker()
            return
        if command == "/settings":
            self.post_output("Settings", self.capture_backend_output(self.backend.print_settings))
            return
        if command == "/help":
            self.post_output("Help", self.capture_backend_output(self.backend.print_help))
            return
        if command == "/new":
            await self.handle_command("/new")
            return
        if command == "/clearimage":
            await self.handle_command("/clearimage")

    async def open_session_picker(self, initial_query: str = "") -> None:
        session_name = await self.push_screen_wait(SessionScreen(initial_query))
        if not session_name:
            self.post_system("Session picker cancelled.")
            return
        await self.handle_command(f"/load {session_name}")

    async def open_model_picker(self, initial_query: str = "") -> None:
        model_name = await self.push_screen_wait(ModelScreen(self.backend, initial_query))
        if not model_name:
            self.post_system("Model picker cancelled.")
            return
        self.backend.config["model"] = model_name
        self.backend.save_config()
        self.post_system(f"Model set to `{model_name}`")
        self.update_status()

    async def open_download(self, initial_query: str = "") -> None:
        model = await self.push_screen_wait(DownloadScreen(self.backend, initial_query))
        if not model:
            self.post_system("Download cancelled.")
            return
        guardrail = self.backend.model_guardrail(model)
        if guardrail["level"] == "heavy":
            proceed = await self.push_screen_wait(ConfirmScreen("Large Model Warning", f"{model['name']} is outside the comfortable {HARDWARE_PROFILE['vram_gb']} GB target for your {HARDWARE_PROFILE['gpu']}.\n\n{guardrail['message']}\n\nPress Enter/Y to continue or Esc/N to cancel."))
            if not proceed:
                self.post_system("Download cancelled after hardware warning.")
                return
        self.post_system(f"Downloading `{model['name']}`...")
        self.pull_model(model)

    @work(thread=True)
    def pull_model(self, model: dict) -> None:
        try:
            self.backend.pull_model(model["name"])
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(self.post_system, f"Download failed for `{model['name']}`: {exc}")
            return
        self.backend.config["model"] = model["name"]
        self.backend.save_config()
        self.call_from_thread(self.post_system, f"Downloaded and activated `{model['name']}`.")
        self.call_from_thread(self.update_status)
        self.call_from_thread(self.update_side_panel)

    @work(thread=True)
    def send_chat(self, prompt: str, images: list[Path]) -> None:
        self.call_from_thread(self.post_system, "Thinking...")
        try:
            reply = self.backend.ollama_chat(prompt, images)
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(self.post_system, f"Chat error: {exc}")
            return
        self.call_from_thread(self.post_assistant, reply)
        self.call_from_thread(self.update_status)

    async def handle_command(self, raw: str) -> None:
        parts = raw.split(maxsplit=2)
        cmd = parts[0].lower()
        argument = raw.split(" ", 1)[1].strip() if len(parts) > 1 else ""

        if cmd == "/" or (not argument and cmd not in {item["name"] for item in COMMAND_CATALOG} and cmd.startswith("/")):
            await self.open_command_palette(cmd.lstrip("/"))
            return

        if cmd == "/help":
            self.post_output("Help", self.capture_backend_output(self.backend.print_help))
            return
        if cmd == "/download":
            await self.open_download(argument)
            return
        if cmd == "/settings":
            self.post_output("Settings", self.capture_backend_output(self.backend.print_settings))
            return
        if cmd == "/model":
            if len(parts) == 1:
                await self.open_model_picker()
            elif len(parts) >= 3 and parts[1].lower() == "set":
                self.backend.config["model"] = parts[2]
                self.backend.save_config()
                self.post_system(f"Model set to `{self.backend.config['model']}`")
                self.update_status()
            else:
                self.post_system("Usage: `/model` or `/model set <name>`")
            return
        if cmd == "/new":
            if self.backend.messages:
                saved = self.backend.save_session()
                self.post_system(f"Saved current session to `{saved.name}`")
            self.backend.session_name = argument or f"session-{now_stamp()}"
            self.backend.messages = []
            self.backend.pending_images = []
            self.compact_header = False
            self.query_one("#chat-log", RichLog).clear()
            self.post_system(f"New session: `{self.backend.session_name}`")
            self.update_status()
            return
        if cmd in {"/session", "/save"}:
            name = argument or self.backend.session_name
            try:
                path = self.backend.save_session(name)
            except Exception as exc:  # noqa: BLE001
                self.post_system(f"Command error: {exc}")
                return
            self.backend.session_name = name
            self.post_system(f"Saved session: `{path.name}`")
            self.update_status()
            return
        if cmd == "/load":
            if not argument:
                await self.open_session_picker()
                return
            try:
                self.backend.load_session(argument)
            except Exception as exc:  # noqa: BLE001
                self.post_system(f"Command error: {exc}")
                return
            self.compact_header = bool(self.backend.messages)
            self.query_one("#chat-log", RichLog).clear()
            self.render_loaded_messages()
            self.post_system(f"Loaded session: `{self.backend.session_name}`")
            self.update_status()
            return
        if cmd == "/sessions":
            await self.open_session_picker()
            return
        if cmd == "/image":
            if not argument:
                self.post_system("Usage: `/image <path>`")
                return
            try:
                image = self.backend.ensure_image(argument)
            except Exception as exc:  # noqa: BLE001
                self.post_system(f"Command error: {exc}")
                return
            self.backend.pending_images.append(image)
            self.post_system(f"Queued image: `{image}`")
            self.update_status()
            return
        if cmd == "/clearimage":
            self.backend.pending_images = []
            self.post_system("Cleared queued images")
            self.update_status()
            return
        if cmd == "/askimg":
            if len(parts) < 2 or "|" not in raw:
                self.post_system("Usage: `/askimg <path> | <prompt>`")
                return
            _, rest = raw.split(" ", 1)
            image_raw, prompt = rest.split("|", 1)
            try:
                image = self.backend.ensure_image(image_raw.strip())
            except Exception as exc:  # noqa: BLE001
                self.post_system(f"Command error: {exc}")
                return
            self.post_user(prompt.strip())
            self.send_chat(prompt.strip(), [image])
            return
        if cmd == "/set":
            if len(parts) < 3:
                self.post_system("Usage: `/set <key> <value>`")
                return
            key = parts[1]
            if key not in self.backend.config:
                self.post_system(f"Unknown setting: `{key}`")
                return
            self.backend.config[key] = self.backend.parse_value(parts[2])
            self.backend.save_config()
            self.post_system(f"Updated `{key}` -> `{self.backend.config[key]}`")
            self.update_status()
            return
        if cmd in {"/exit", "/quit"}:
            try:
                self.backend.save_session()
            except Exception as exc:  # noqa: BLE001
                self.post_system(f"Command error: {exc}")
                return
            self.exit()
            return

        self.post_system(f"Unknown command: `{cmd}`")

    @on(Input.Submitted, "#input")
    async def on_submit(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        event.input.value = ""
        if not value:
            return
        if value.startswith("/"):
            try:
                await self.handle_command(value)
            except Exception as exc:  # noqa: BLE001
                self.post_system(f"Command error: {exc}")
            return
        queued = self.backend.pending_images[:]
        self.backend.pending_images = []
        self.post_user(value)
        self.update_status()
        self.send_chat(value, queued)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    backend = KaiZenCLI()
    if len(sys.argv) > 1 and sys.argv[1] in {"--help", "-h", "help"}:
        backend.print_banner()
        print()
        backend.print_help()
        return 0
    if len(sys.argv) > 1 and sys.argv[1] in {"--legacy", "legacy"}:
        return backend.loop()

    app = KaiZenTUI()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

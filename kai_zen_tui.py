import io
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

from kai_zen_cli import KaiZenCLI, LOGO_PATH, MODEL_CATALOG, SESSIONS_DIR, now_stamp


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

    def compose(self) -> ComposeResult:
        with Container(id="download-shell"):
            yield Static("Kai-zen Model Download", id="download-title")
            yield Input(value=self.initial_query, placeholder="Search models", id="download-search")
            yield ListView(id="download-list")
            yield Static(id="download-meta")

    def on_mount(self) -> None:
        self.refresh_models(self.initial_query)
        self.query_one("#download-search", Input).focus()

    def build_item(self, model: dict) -> ListItem:
        installed = model["name"] in self.backend.installed_models()
        installed_text = "installed" if installed else "available"
        line = Text()
        line.append(model["label"], style="bold #e4e4ea")
        line.append(f"  [{model['name']}]  ", style="#8e8e99")
        line.append(model["size"], style="#c6b3ff")
        line.append("  ")
        line.append(installed_text, style="#b79cff" if installed else "#6f7685")
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
        text = Text()
        text.append(f"{model['label']}\n", style="bold #e4e4ea")
        text.append(f"modality: {model['modality']}    ", style="#b79cff")
        text.append(f"vram: {model['vram']}    ", style="#bcbcc7")
        text.append(f"speed: {model['speed']}\n", style="#c6b3ff")
        text.append(f"tags: {tags}", style="#8e8e99")
        self.query_one("#download-meta", Static).update(text)

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
                yield Input(placeholder="Message Kai-zen or type /help", id="input")
                yield Static("Enter sends. Slash commands: /help /download /model /session /image /settings", id="command-hint")
            yield Footer()

    def on_mount(self) -> None:
        self.compact_header = bool(self.backend.messages)
        self.update_hero()
        self.update_status()
        self.update_side_panel()
        self.post_system("Kai-zen TUI ready. `/download` opens the model picker.")
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
        for binary_name, command in (
            ("chafa", ["--symbols", "vhalf+braille", "--size", "30x10", "--colors", "full"]),
            ("ascii-image-converter", ["-C", "-b", "-W", "30"]),
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
        panel.append("/download qwen\n/download vision\n/model\n/settings\n/sessions\n", style="#8e8e99")
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

    def capture_backend_output(self, fn) -> str:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            fn()
        return buffer.getvalue().strip()

    async def open_download(self, initial_query: str = "") -> None:
        model = await self.push_screen_wait(DownloadScreen(self.backend, initial_query))
        if not model:
            self.post_system("Download cancelled.")
            return
        self.post_system(f"Downloading `{model['name']}`...")
        self.pull_model(model)

    @work(thread=True)
    def pull_model(self, model: dict) -> None:
        binary = shutil.which("ollama")
        if not binary:
            self.call_from_thread(self.post_system, "Ollama is not installed or not on PATH.")
            return
        try:
            subprocess.run([binary, "pull", model["name"]], check=True)
        except subprocess.CalledProcessError as exc:
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

        if cmd == "/help":
            self.post_output("Help", self.capture_backend_output(self.backend.print_help))
            return
        if cmd == "/download":
            query = raw.split(" ", 1)[1].strip() if len(parts) > 1 else ""
            await self.open_download(query)
            return
        if cmd == "/settings":
            self.post_output("Settings", self.capture_backend_output(self.backend.print_settings))
            return
        if cmd == "/model":
            if len(parts) == 1:
                self.post_system(f"Active model: `{self.backend.config['model']}`")
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
            self.backend.session_name = parts[1] if len(parts) > 1 else f"session-{now_stamp()}"
            self.backend.messages = []
            self.backend.pending_images = []
            self.compact_header = False
            self.query_one("#chat-log", RichLog).clear()
            self.post_system(f"New session: `{self.backend.session_name}`")
            self.update_status()
            return
        if cmd in {"/session", "/save"}:
            name = parts[1] if len(parts) > 1 else self.backend.session_name
            path = self.backend.save_session(name)
            self.backend.session_name = name
            self.post_system(f"Saved session: `{path.name}`")
            self.update_status()
            return
        if cmd == "/load":
            if len(parts) < 2:
                self.post_system("Usage: `/load <name>`")
                return
            self.backend.load_session(parts[1])
            self.compact_header = bool(self.backend.messages)
            self.query_one("#chat-log", RichLog).clear()
            self.post_system(f"Loaded session: `{self.backend.session_name}`")
            self.update_status()
            return
        if cmd == "/sessions":
            names = "\n".join(f"- {p.stem}" for p in sorted(SESSIONS_DIR.glob("*.json"))) or "- none"
            self.post_output("Sessions", names)
            return
        if cmd == "/image":
            if len(parts) < 2:
                self.post_system("Usage: `/image <path>`")
                return
            image = self.backend.ensure_image(parts[1])
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
            image = self.backend.ensure_image(image_raw.strip())
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
            self.backend.save_session()
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
            await self.handle_command(value)
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

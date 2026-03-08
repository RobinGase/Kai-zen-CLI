import json
import sys
import textwrap
import urllib.error
import urllib.request
from base64 import b64encode
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from PIL import Image


APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
SESSIONS_DIR = APP_DIR / "sessions"
LOGO_PATH = Path(r"C:\Users\Robin\Desktop\RRTECH\Assets\KaizenInnovations\logoEmblem.png")

DEFAULT_CONFIG = {
    "backend": "ollama",
    "base_url": "http://127.0.0.1:11434",
    "model": "qwen3.5:0.8b",
    "model_path": r"D:\Robindevwindows\Kai-Qwen models\Qwen0-8B",
    "temperature": 0.7,
    "top_p": 0.9,
    "num_predict": 512,
    "think": False,
    "stream": False,
    "keep_alive": "5m",
    "system_prompt": "You are Qwen 3.5 running inside Kai-zen CLI. Be concise, helpful, and honest about limitations.",
}


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def slugify(value: str) -> str:
    allowed = []
    for ch in value.strip().replace(" ", "-"):
        if ch.isalnum() or ch in {"-", "_"}:
            allowed.append(ch)
    result = "".join(allowed).strip("-_")
    return result or f"session-{now_stamp()}"


class KaiZenCLI:
    def __init__(self) -> None:
        self.config = self.load_config()
        self.session_name = f"session-{now_stamp()}"
        self.messages = []
        self.pending_images = []

    def load_config(self) -> dict:
        if CONFIG_PATH.exists():
            with CONFIG_PATH.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            config = deepcopy(DEFAULT_CONFIG)
            config.update(loaded)
            return config
        self.save_config(DEFAULT_CONFIG)
        return deepcopy(DEFAULT_CONFIG)

    def save_config(self, config: dict | None = None) -> None:
        CONFIG_PATH.write_text(
            json.dumps(config or self.config, indent=2),
            encoding="utf-8",
        )

    def session_path(self, name: str | None = None) -> Path:
        return SESSIONS_DIR / f"{slugify(name or self.session_name)}.json"

    def save_session(self, name: str | None = None) -> Path:
        target_name = name or self.session_name
        payload = {
            "session_name": target_name,
            "saved_at": datetime.now().isoformat(),
            "model": self.config["model"],
            "messages": self.messages,
        }
        path = self.session_path(target_name)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def load_session(self, name: str) -> None:
        path = self.session_path(name)
        if not path.exists():
            raise FileNotFoundError(f"Session not found: {path.name}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.session_name = payload.get("session_name", name)
        self.messages = payload.get("messages", [])
        self.pending_images = []

    def list_sessions(self) -> list[Path]:
        return sorted(SESSIONS_DIR.glob("*.json"))

    def render_logo(self) -> str:
        if not LOGO_PATH.exists():
            return "[ Kai-zen CLI ]"
        try:
            chars = " .:-=+*#%@"
            image = Image.open(LOGO_PATH).convert("L")
            width = 40
            aspect = image.height / image.width if image.width else 1
            height = max(12, int(width * aspect * 0.45))
            image = image.resize((width, height))
            lines = []
            for y in range(height):
                row = []
                for x in range(width):
                    pixel = image.getpixel((x, y))
                    row.append(chars[pixel * (len(chars) - 1) // 255])
                lines.append("".join(row).rstrip())
            return "\n".join(line for line in lines if line.strip())
        except Exception:
            return "[ Kai-zen CLI ]"

    def print_banner(self) -> None:
        print(self.render_logo())
        print("Kai-zen CLI")
        print(f"- backend: {self.config['backend']}")
        print(f"- model:   {self.config['model']}")
        print(f"- path:    {self.config['model_path']}")
        print(f"- session: {self.session_name}")
        print("- /help for commands")

    def print_help(self) -> None:
        print(
            textwrap.dedent(
                """
                Kai-zen CLI Commands
                - /help                      List all commands
                - /new [name]                Start a fresh session
                - /session [name]            Save current session, optionally with a name
                - /save [name]               Save current session
                - /load <name>               Load a saved session
                - /sessions                  List saved sessions
                - /model                     Show current model
                - /model set <name>          Set the active model
                - /image <path>              Queue an image for the next prompt
                - /clearimage                Clear queued image attachments
                - /askimg <path> | <prompt>  Send one multimodal prompt immediately
                - /settings                  Show runtime settings
                - /set <key> <value>         Change a setting and persist it
                - /exit                      Save and quit
                - /quit                      Save and quit

                Current settings keys
                - backend, base_url, model, model_path
                - temperature, top_p, num_predict
                - think, stream, keep_alive, system_prompt
                """
            ).strip()
        )

    def print_settings(self) -> None:
        print(json.dumps(self.config, indent=2))

    def parse_value(self, value: str):
        lowered = value.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return value

    def ensure_image(self, path_str: str) -> Path:
        path = Path(path_str.strip().strip('"'))
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")
        if not path.is_file():
            raise FileNotFoundError(f"Image is not a file: {path}")
        return path

    def encode_images(self, images: list[Path]) -> list[str]:
        encoded = []
        for image in images:
            encoded.append(b64encode(image.read_bytes()).decode("ascii"))
        return encoded

    def api_message(self, role: str, prompt: str, images: list[Path] | None = None) -> dict:
        message = {"role": role, "content": prompt}
        if images:
            message["images"] = self.encode_images(images)
        return message

    def ollama_chat(self, prompt: str, images: list[Path] | None = None) -> str:
        images = images or []
        payload = {
            "model": self.config["model"],
            "stream": self.config["stream"],
            "keep_alive": self.config["keep_alive"],
            "messages": [
                {"role": "system", "content": self.config["system_prompt"]},
                *self.messages,
                self.api_message("user", prompt, images),
            ],
            "options": {
                "temperature": self.config["temperature"],
                "top_p": self.config["top_p"],
                "num_predict": self.config["num_predict"],
            },
            "think": self.config["think"],
        }

        request = urllib.request.Request(
            url=f"{self.config['base_url'].rstrip('/')}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cannot reach Ollama at {self.config['base_url']}") from exc

        message = data.get("message", {})
        content = message.get("content", "")
        if not content:
            raise RuntimeError("Model returned an empty response")
        self.messages.append(self.api_message("user", prompt, images))
        self.messages.append({"role": "assistant", "content": content})
        return content

    def run_prompt(self, prompt: str, images: list[Path] | None = None) -> None:
        reply = self.ollama_chat(prompt, images)
        print(f"\n{self.config['model']}\n{reply}\n")

    def handle_command(self, raw: str) -> bool:
        parts = raw.split(maxsplit=2)
        cmd = parts[0].lower()

        if cmd == "/help":
            self.print_help()
            return True

        if cmd == "/new":
            if self.messages:
                saved = self.save_session()
                print(f"Saved current session to {saved.name}")
            self.session_name = parts[1] if len(parts) > 1 else f"session-{now_stamp()}"
            self.messages = []
            self.pending_images = []
            print(f"New session: {self.session_name}")
            return True

        if cmd in {"/session", "/save"}:
            name = parts[1] if len(parts) > 1 else self.session_name
            path = self.save_session(name)
            self.session_name = name
            print(f"Saved session: {path.name}")
            return True

        if cmd == "/load":
            if len(parts) < 2:
                print("Usage: /load <name>")
                return True
            self.load_session(parts[1])
            print(f"Loaded session: {self.session_name}")
            return True

        if cmd == "/sessions":
            sessions = self.list_sessions()
            if not sessions:
                print("No saved sessions yet.")
                return True
            for item in sessions:
                print(f"- {item.stem}")
            return True

        if cmd == "/model":
            if len(parts) == 1:
                print(self.config["model"])
                return True
            if len(parts) >= 3 and parts[1].lower() == "set":
                self.config["model"] = parts[2]
                self.save_config()
                print(f"Model set to {self.config['model']}")
                return True
            print("Usage: /model OR /model set <name>")
            return True

        if cmd == "/image":
            if len(parts) < 2:
                print("Usage: /image <path>")
                return True
            image = self.ensure_image(parts[1])
            self.pending_images.append(image)
            print(f"Queued image: {image}")
            return True

        if cmd == "/clearimage":
            self.pending_images = []
            print("Cleared queued images")
            return True

        if cmd == "/askimg":
            if len(parts) < 2 or "|" not in raw:
                print("Usage: /askimg <path> | <prompt>")
                return True
            _, rest = raw.split(" ", 1)
            image_raw, prompt = rest.split("|", 1)
            image = self.ensure_image(image_raw.strip())
            self.run_prompt(prompt.strip(), [image])
            return True

        if cmd == "/settings":
            self.print_settings()
            return True

        if cmd == "/set":
            if len(parts) < 3:
                print("Usage: /set <key> <value>")
                return True
            key = parts[1]
            if key not in self.config:
                print(f"Unknown setting: {key}")
                return True
            self.config[key] = self.parse_value(parts[2])
            self.save_config()
            print(f"Updated {key} -> {self.config[key]}")
            return True

        if cmd in {"/exit", "/quit"}:
            path = self.save_session()
            print(f"Saved session: {path.name}")
            return False

        print("Unknown command. Type /help")
        return True

    def loop(self) -> int:
        self.print_banner()
        while True:
            try:
                raw = input("\nYou> ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nExiting...")
                self.save_session()
                return 0

            if not raw:
                continue

            if raw.startswith("/"):
                try:
                    keep_running = self.handle_command(raw)
                except Exception as exc:  # noqa: BLE001
                    print(f"Command error: {exc}")
                    keep_running = True
                if not keep_running:
                    return 0
                continue

            try:
                queued = self.pending_images[:]
                self.pending_images = []
                self.run_prompt(raw, queued)
            except Exception as exc:  # noqa: BLE001
                print(f"Chat error: {exc}")


def main() -> int:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    cli = KaiZenCLI()
    if len(sys.argv) > 1 and sys.argv[1] in {"--help", "-h", "help"}:
        cli.print_banner()
        print()
        cli.print_help()
        return 0
    return cli.loop()


if __name__ == "__main__":
    raise SystemExit(main())

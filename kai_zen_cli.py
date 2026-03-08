import json
import os
import shutil
import subprocess
import sys
import tempfile
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
ANSI_RESET = "\033[0m"
ANSI_CYAN = "\033[96m"
ANSI_BLUE = "\033[94m"
ANSI_DIM = "\033[2m"
ANSI_GOLD = "\033[93m"
ANSI_VIOLET = "\033[95m"

MODEL_CATALOG = [
    {"name": "qwen3.5:0.8b", "label": "Qwen 3.5 0.8B", "size": "1.0 GB", "modality": "text", "vram": "4GB+", "speed": "very fast", "tags": ["qwen", "0.8b", "small", "text"]},
    {"name": "qwen3.5:2b", "label": "Qwen 3.5 2B", "size": "1.6 GB", "modality": "text", "vram": "6GB+", "speed": "fast", "tags": ["qwen", "2b", "small", "text"]},
    {"name": "qwen3.5:4b", "label": "Qwen 3.5 4B", "size": "2.6 GB", "modality": "text", "vram": "8GB+", "speed": "fast", "tags": ["qwen", "4b", "text", "balanced"]},
    {"name": "qwen3.5:9b", "label": "Qwen 3.5 9B", "size": "5.5 GB", "modality": "text", "vram": "10GB+", "speed": "medium", "tags": ["qwen", "9b", "text", "quality"]},
    {"name": "qwen2.5vl:3b", "label": "Qwen 2.5 VL 3B", "size": "5.2 GB", "modality": "multimodal", "vram": "8GB+", "speed": "medium", "tags": ["qwen", "vision", "vl", "3b", "multimodal"]},
    {"name": "qwen2.5vl:7b", "label": "Qwen 2.5 VL 7B", "size": "8.4 GB", "modality": "multimodal", "vram": "12GB+", "speed": "slower", "tags": ["qwen", "vision", "vl", "7b", "multimodal"]},
    {"name": "llama3.2:3b", "label": "Llama 3.2 3B", "size": "2.0 GB", "modality": "text", "vram": "6GB+", "speed": "fast", "tags": ["llama", "3b", "text"]},
    {"name": "llama3.1:8b", "label": "Llama 3.1 8B", "size": "4.7 GB", "modality": "text", "vram": "10GB+", "speed": "medium", "tags": ["llama", "8b", "text"]},
    {"name": "phi4:mini", "label": "Phi 4 Mini", "size": "2.5 GB", "modality": "text", "vram": "8GB+", "speed": "fast", "tags": ["phi", "mini", "text", "small"]},
    {"name": "mistral:7b", "label": "Mistral 7B", "size": "4.1 GB", "modality": "text", "vram": "8GB+", "speed": "medium", "tags": ["mistral", "7b", "text"]},
    {"name": "gemma2:2b", "label": "Gemma 2 2B", "size": "1.6 GB", "modality": "text", "vram": "6GB+", "speed": "fast", "tags": ["gemma", "2b", "small", "text"]},
    {"name": "gemma2:9b", "label": "Gemma 2 9B", "size": "5.4 GB", "modality": "text", "vram": "10GB+", "speed": "medium", "tags": ["gemma", "9b", "text", "quality"]},
]

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

    def color_enabled(self) -> bool:
        return sys.stdout.isatty() and not self.config.get("no_color", False)

    def rgb(self, text: str, r: int, g: int, b: int) -> str:
        if not self.color_enabled():
            return text
        return f"\033[38;2;{r};{g};{b}m{text}{ANSI_RESET}"

    def style(self, text: str, code: str) -> str:
        if not self.color_enabled():
            return text
        return f"{code}{text}{ANSI_RESET}"

    def render_logo(self) -> str:
        art = self.render_logo_with_converter()
        if not art:
            art = self.render_logo_fallback()
        w = 58
        use_color = self.color_enabled()
        border = self.rgb("=" * w, 10, 30, 110) if use_color else "=" * w
        title_text = "K A I - Z E N   C L I"
        sub_text = "Local Qwen Test Console"
        if use_color:
            title = self.rgb(title_text.center(w), 31, 123, 255)
            sub = self.rgb(sub_text.center(w), 217, 75, 255)
        else:
            title = title_text.center(w)
            sub = sub_text.center(w)
        return "\n".join(["", border, "", *art, "", border, title, sub, border, ""])

    def render_logo_with_converter(self) -> list[str]:
        art = self.render_logo_with_chafa()
        if art:
            return art

        if not LOGO_PATH.exists():
            return []
        binary = shutil.which("ascii-image-converter")
        if not binary:
            return []
        try:
            source = self.prepare_logo_source()
            if self.color_enabled():
                command = [binary, str(source), "-b", "-W", "56", "-C"]
            else:
                command = [binary, str(source), "-c", "-W", "42"]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=True,
            )
        except Exception:
            return []
        lines = [line.rstrip() for line in result.stdout.splitlines()]
        return [line for line in lines if line.strip()]

    def render_logo_with_chafa(self) -> list[str]:
        if not LOGO_PATH.exists():
            return []
        binary = shutil.which("chafa")
        if not binary:
            return []
        try:
            source = self.prepare_logo_source()
            command = [
                binary,
                "--format",
                "symbols",
                "--polite",
                "on",
                "--animate",
                "off",
                "--bg",
                "000000",
                "--optimize",
                "0",
            ]
            if self.color_enabled():
                command += ["--symbols", "vhalf+braille", "--size", "56x26", "--colors", "full"]
            else:
                command += ["--symbols", "ascii+space+border", "--size", "40x18", "--colors", "none"]
            command.append(str(source))

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=True,
            )
        except Exception:
            return []
        lines = [line.rstrip() for line in result.stdout.splitlines()]
        return [line for line in lines if line.strip()]

    def prepare_logo_source(self) -> Path:
        with Image.open(LOGO_PATH) as image:
            rgba = image.convert("RGBA")
            alpha = rgba.getchannel("A")
            bbox = alpha.getbbox()
            if bbox:
                rgba = rgba.crop(bbox)

            width, height = rgba.size
            scale = 2
            resized = rgba.resize((max(1, width * scale), max(1, height * scale)), Image.LANCZOS)

            temp_dir = Path(tempfile.gettempdir()) / "kai_zen_cli"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_path = temp_dir / "logo_cropped.png"
            resized.save(temp_path)
            return temp_path

    def render_logo_fallback(self) -> list[str]:
        raw_lines = [
            "___________________________SS___________________________",
            "__________________________SSS___________________________",
            "________________________SSSS____________________________",
            "______________________SSSSS_______bbb__________________",
            "____________________SSSSS_______bbbbb__________________",
            "___________________SSSS_______bbbbbbb__________________",
            "_________________SSS________bbbbbbbb___________________",
            "________________SS________bbbbbbbbb____________________",
            "_______________S________bbbbbbbbbb_____________________",
            "__________________________bbbbbBBBbb____SS______________",
            "________________________bbbBBBBBBBBbb__SSSS_____________",
            "______________________bbbBBBBBBBBBBBb_SSSSS____________",
            "____________________bbBBBBBBBBBBBBBBbbSSSS_____________",
            "__________________bbBBBBBBBBBBBBBBBBBbSSS______________",
            "________________bbBBBBBBBBBBBBBBBBBBBbS________________",
            "______________bbBBBBBBBBBBBBBBBBBBBBBBb_________________",
            "____________bbBBBBBBBBBBBBBBBBBBBBBBBb__________________",
            "__________bbBBBBBBBBBBBBBBBBBBBBBBBBb___________________",
            "________bbBBBBBBBBBBBGGGGGGGGGGBBBBb____________________",
            "______bbBBBBBBBBBBGGGGGGGGGGGGGGBBb_____________________",
            "____bbBBBBBBBBBGGGGGGGGGGGGGGGGGBb______________________",
            "__bbBBBBBBBBGGGGGGGGGGGGGGGGGGGBb_______________________",
            "_bBBBBBBBGGGGGGGGGGVVVVVVVVVVVVb________________________",
            "__BBBBBGGGGGGGGVVVVVVVVVVVVVVVb_________________________",
            "___BBBBGGGGGVVVVVVVVVVVVVVVVVb__________________________",
            "____BBBBGGVVVVVVVVVVVVVVVVVVb___________________________",
            "_____BBBbVVVVVVVVVVVVVVVVVVb____________________________",
            "______Bb__VVVVVVVVVVVVVVVVb_____________________________",
            "_______b____VVVVVVVVVVVVVb______________________________",
            "________________VVVVVVVVb____SS_________________________",
            "__________________VVVVVb___SSSS__________________________",
            "____________________VVb__SSSSS__________________________",
            "______________________b_SSSS____________________________",
            "_______________________SSSS_____________________________",
            "______________________SSS_______________________________",
        ]
        color_map = {
            "B": (10, 30, 110),
            "b": (31, 123, 255),
            "G": (243, 229, 93),
            "V": (130, 40, 220),
            "S": (182, 181, 214),
        }
        glyph_map = {"B": "%", "b": "/", "G": "|", "V": "%", "S": "~", "_": " "}
        rendered = []
        for raw in raw_lines:
            row = []
            for ch in raw:
                glyph = glyph_map.get(ch, ch)
                if self.color_enabled() and ch in color_map:
                    r, g, b = color_map[ch]
                    row.append(f"\033[38;2;{r};{g};{b}m{glyph}{ANSI_RESET}")
                else:
                    row.append(glyph)
            rendered.append("".join(row).rstrip())
        return [line for line in rendered if line.strip()]

    def print_banner(self) -> None:
        print(self.render_logo())
        print(self.style("Kai-zen CLI", ANSI_CYAN))
        print(f"- backend: {self.style(self.config['backend'], ANSI_BLUE)}")
        print(f"- model:   {self.style(self.config['model'], ANSI_GOLD)}")
        print(f"- path:    {self.config['model_path']}")
        print(f"- session: {self.style(self.session_name, ANSI_VIOLET)}")
        print(f"- queued:  {self.style(str(len(self.pending_images)), ANSI_VIOLET)} image(s)")
        print(f"- /help for commands")

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
                - /download                  Open searchable model picker
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
                - think, stream, keep_alive, system_prompt, no_color
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

    def installed_models(self) -> set[str]:
        binary = shutil.which("ollama")
        if not binary:
            return set()
        try:
            result = subprocess.run(
                [binary, "list"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=True,
            )
        except Exception:
            return set()

        installed = set()
        for line in result.stdout.splitlines()[1:]:
            stripped = line.strip()
            if not stripped:
                continue
            installed.add(stripped.split()[0])
        return installed

    def filter_model_catalog(self, query: str) -> list[dict]:
        query = query.strip().lower()
        if not query:
            return MODEL_CATALOG[:]

        filtered = []
        for model in MODEL_CATALOG:
            haystack = " ".join([model["name"], model["label"], *model["tags"]]).lower()
            if query in haystack:
                filtered.append(model)
        return filtered

    def clear_screen(self) -> None:
        if os.name == "nt":
            os.system("cls")
        else:
            os.system("clear")

    def model_badges(self, model: dict) -> str:
        parts = [
            self.style(model["modality"], ANSI_VIOLET),
            self.style(model["vram"], ANSI_BLUE),
            self.style(model["speed"], ANSI_GOLD),
        ]
        return " | ".join(parts)

    def render_model_picker(self, query: str, selected: int, filtered: list[dict], installed: set[str], offset: int) -> None:
        self.clear_screen()
        print(self.style("Kai-zen Model Download", ANSI_CYAN))
        print("Type to search. Up/Down to move. Enter to download. Esc to cancel. Backspace to edit.\n")
        print(f"Search: {self.style(query or 'all models', ANSI_GOLD)}")
        print(f"Matches: {self.style(str(len(filtered)), ANSI_BLUE)}\n")

        if not filtered:
            print("No models match your search.")
            return

        window = filtered[offset:offset + 12]
        for index, model in enumerate(window):
            cursor = ">" if index == selected else " "
            installed_mark = self.style("installed", ANSI_VIOLET) if model["name"] in installed else self.style("available", ANSI_DIM)
            line = f"{cursor} {model['label']}  [{model['name']}]"
            if index == selected:
                line = self.style(line, ANSI_BLUE)
            print(line)
            print(f"   {model['size']}  |  {self.model_badges(model)}  |  {installed_mark}")
            print(f"   tags: {', '.join(model['tags'])}")

        shown_to = min(len(filtered), offset + len(window))
        print(f"\nShowing {offset + 1}-{shown_to} of {len(filtered)}")

    def select_download_model(self, query: str = "") -> dict | None:
        try:
            import msvcrt  # type: ignore
        except ImportError:
            return self.select_download_model_fallback(query)

        installed = self.installed_models()
        selected = 0
        offset = 0
        page_size = 12
        while True:
            filtered = self.filter_model_catalog(query)
            if selected >= max(1, len(filtered)):
                selected = max(0, len(filtered) - 1)
            if selected < offset:
                offset = selected
            elif selected >= offset + page_size:
                offset = selected - page_size + 1
            self.render_model_picker(query, selected - offset, filtered, installed, offset)

            key = msvcrt.getwch()
            if key in {"\r", "\n"}:
                if filtered:
                    self.clear_screen()
                    return filtered[selected]
                continue
            if key == "\x1b":
                self.clear_screen()
                return None
            if key in {"\b", "\x7f"}:
                query = query[:-1]
                selected = 0
                offset = 0
                continue
            if key in {"\x00", "\xe0"}:
                arrow = msvcrt.getwch()
                if arrow == "H" and selected > 0:
                    selected -= 1
                elif arrow == "P" and selected < max(0, len(filtered) - 1):
                    selected += 1
                elif arrow == "I":
                    selected = max(0, selected - page_size)
                elif arrow == "Q":
                    selected = min(max(0, len(filtered) - 1), selected + page_size)
                continue
            if key.isprintable():
                query += key
                selected = 0
                offset = 0

    def select_download_model_fallback(self, query: str = "") -> dict | None:
        while True:
            filtered = self.filter_model_catalog(query)
            print(self.style("Kai-zen Model Download", ANSI_CYAN))
            print(f"Search: {query or 'all models'}")
            for index, model in enumerate(filtered[:10], start=1):
                print(f"{index}. {model['label']} [{model['name']}] {model['size']}")
                print(f"   {model['modality']} | {model['vram']} | {model['speed']} | {', '.join(model['tags'])}")
            choice = input("Search text, number, or blank to cancel> ").strip()
            if not choice:
                return None
            if choice.isdigit() and 1 <= int(choice) <= min(len(filtered), 10):
                return filtered[int(choice) - 1]
            query = choice

    def download_model(self, initial_query: str = "") -> None:
        binary = shutil.which("ollama")
        if not binary:
            raise RuntimeError("Ollama is not installed or not on PATH")

        model = self.select_download_model(initial_query)
        if not model:
            print("Download cancelled")
            return

        print(f"Downloading {self.style(model['name'], ANSI_GOLD)}...\n")
        subprocess.run([binary, "pull", model["name"]], check=True)

        set_active = input(f"Set {model['name']} as active model? [Y/n] ").strip().lower()
        if set_active in {"", "y", "yes"}:
            self.config["model"] = model["name"]
            self.save_config()
            print(f"Active model set to {self.config['model']}")
        else:
            print(f"Downloaded {model['name']}")

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
        print(f"\n{self.style(self.config['model'], ANSI_GOLD)}\n{reply}\n")

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

        if cmd == "/download":
            initial_query = ""
            if len(parts) > 1:
                initial_query = raw.split(" ", 1)[1].strip()
            self.download_model(initial_query)
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
                raw = input(f"\n{self.style('You', ANSI_CYAN)}> ").strip()
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
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
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

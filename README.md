# Kai-zen CLI

Simple local TUI/CLI chat for testing Qwen models, starting with `qwen3.5:0.8b`.

## Current setup

- Backend: `Ollama`
- Default model: `qwen3.5:0.8b`
- Default model path placeholder: `./models/Qwen0-8B`
- Bundled logo asset: `assets/logoEmblem.png`

Note: the reserved model directory is currently empty, so this first version runs through your installed local Ollama model while keeping the target path in config for later local-path work.

## Run

```bat
run_kai_zen_cli.bat
kaizen
```

The default launch now opens the TUI. To use the older plain chat loop:

```bat
python kai_zen_tui.py --legacy
```

## Commands

- `/help`
- `/new [name]`
- `/session [name]`
- `/save [name]`
- `/load <name>`
- `/sessions`
- `/model`
- `/model set <name>`
- `/download`
- `/image <path>`
- `/clearimage`
- `/askimg <path> | <prompt>`
- `/settings`
- `/set <key> <value>`
- `/exit`

Color can be disabled with:

```text
/set no_color true
```

Remote backend override:

```text
KAI_ZEN_BASE_URL=http://your-model-host:11434
```

## Good first tests

```text
/settings
/model
Describe yourself in one sentence.
/askimg D:\path\to\image.png | Describe this image briefly.
```

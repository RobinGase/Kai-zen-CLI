# Kai-zen CLI

Simple local CLI chat for testing Qwen models, starting with `qwen3.5:0.8b`.

## Current setup

- Backend: `Ollama`
- Default model: `qwen3.5:0.8b`
- Reserved local model path: `D:\Robindevwindows\Kai-Qwen models\Qwen0-8B`

Note: the reserved model directory is currently empty, so this first version runs through your installed local Ollama model while keeping the target path in config for later local-path work.

## Run

```bat
D:\Robindevwindows\Kai-Zen-CLI\run_kai_zen_cli.bat
kaizen
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
- `/image <path>`
- `/clearimage`
- `/askimg <path> | <prompt>`
- `/settings`
- `/set <key> <value>`
- `/exit`

## Good first tests

```text
/settings
/model
Describe yourself in one sentence.
/askimg D:\path\to\image.png | Describe this image briefly.
```

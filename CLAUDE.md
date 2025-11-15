# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MCP server that bridges MCP clients (like Claude Desktop) with Sonic Pi for live coding music. Uses python-sonic (psonic) to send OSC messages to Sonic Pi's daemon.

## Development Commands

```bash
# Install dependencies
uv sync

# Run the MCP server (for development)
uv run mcp-musicbox/server.py

# Lint code
uv run ruff check .

# Format code
uv run ruff format .
```

## Architecture

### MCP Server (`mcp-musicbox/server.py`)

Single-file FastMCP server exposing these tools:
- `initialize_sonic_pi()` - Starts Sonic Pi app and establishes connection
- `reconnect_sonic_pi()` - Reconnects without restarting (for session recovery)
- `play_music(code)` - Executes Sonic Pi Ruby code
- `stop_music()` - Stops all audio
- `change_mix(parameters)` - Updates live mix parameters via Time State
- `read_shared_state()` - Reads current parameter values
- `debug_sonic_pi_connection()` - Shows connection diagnostics

### Connection Flow

1. Server parses `~/.sonic-pi/log/daemon.log` to extract:
   - Daemon token
   - GUI port (`gui-send-to-spider`)
   - OSC port (`osc-cues`)
2. Calls `psonic.set_server_parameter()` with these values
3. Uses `psonic.run()` to send code and `psonic.stop()` to halt playback

### Live Mix System

Parameters are stored in a JSON file (path configured via `SHARED_STATE_PATH`) and sent to Sonic Pi via Time State (`set :param, value`). This allows real-time effect control without stopping music.

## Key Configuration

- `SONIC_PI_APP_PATH` - macOS app location (default: `/Applications/Sonic Pi.app`)
- `SHARED_STATE_PATH` - Path to shared_state.json for live parameters (must be configured)

## Dependencies

- `mcp` - Model Context Protocol SDK
- `python-sonic` (psonic) - Python-to-Sonic Pi bridge
- `python-osc` - OSC protocol support
- `ruff` - Linting and formatting

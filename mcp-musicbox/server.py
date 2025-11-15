#!/usr/bin/env python3
"""
IMPROVED MCP Server for Sonic Pi with persistent connections and shared state
"""

import subprocess
import time
import re
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("musicbox")

try:
    from psonic import *
    PSONIC_AVAILABLE = True
except ImportError:
    PSONIC_AVAILABLE = False

# Known app location and state file
SONIC_PI_APP_PATH = "/Applications/Sonic Pi.app"
SHARED_STATE_PATH = "/YourPathNameHere"

# Track connection state
_psonic_connected = False


def check_sonic_pi_running():
    """Check if Sonic Pi is running on macOS"""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "Sonic Pi"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_sonic_pi_log_path():
    """Get the path to Sonic Pi's daemon log file"""
    return Path.home() / ".sonic-pi" / "log" / "daemon.log"


def parse_sonic_pi_connection_params():
    """Parse Sonic Pi's GUI log to extract connection parameters (v4.6+ format)"""
    gui_log_path = Path.home() / ".sonic-pi" / "log" / "gui.log"

    if not gui_log_path.exists():
        return None, None, None, None

    try:
        # Read GUI log as binary since it contains binary data
        import subprocess
        result = subprocess.run(
            ["strings", str(gui_log_path)],
            capture_output=True,
            text=True,
            timeout=5
        )
        log_content = result.stdout

        gui_port = None
        osc_port = None
        token = None

        # Parse Spider port (gui-send-to-spider)
        spider_match = re.search(r'Setting up OSC sender to Spider on port (\d+)', log_content)
        if spider_match:
            gui_port = int(spider_match.group(1))

        # Parse Tau port (osc-cues)
        tau_match = re.search(r'Setting up OSC sender to Tau on port (\d+)', log_content)
        if tau_match:
            osc_port = int(tau_match.group(1))

        # Parse token from daemon_stdout lines (it's the large number)
        token_candidates = re.findall(r'daemon_stdout: (\d+)', log_content)
        for candidate in token_candidates:
            if len(candidate) > 6:  # Token is a large number
                token = int(candidate)
                break

        ip_address = "127.0.0.1"

        return ip_address, gui_port, osc_port, token

    except Exception as e:
        print(f"Error parsing gui.log: {e}")
        return None, None, None, None


def start_sonic_pi():
    """Start Sonic Pi application"""
    try:
        if Path(SONIC_PI_APP_PATH).exists():
            subprocess.Popen(["open", SONIC_PI_APP_PATH])
            return True
        return False
    except Exception:
        return False


def connect_to_sonic_pi():
    """Connect psonic to Sonic Pi - DOES NOT start or stop Sonic Pi"""
    global _psonic_connected
    
    if not PSONIC_AVAILABLE:
        return False, "psonic library not available"
    
    if not check_sonic_pi_running():
        return False, "Sonic Pi not running"
    
    # Parse connection parameters
    ip, gui_port, osc_port, token = parse_sonic_pi_connection_params()
    
    if not all([ip, gui_port, osc_port, token]):
        return False, f"Could not read connection parameters (IP={ip}, GUI={gui_port}, OSC={osc_port}, Token={token})"
    
    try:
        set_server_parameter(ip, token, gui_port, osc_port)
        # Test connection without stopping music
        _psonic_connected = True
        return True, f"Connected to Sonic Pi at {ip}:{gui_port}"
    except Exception as e:
        _psonic_connected = False
        return False, f"Connection failed: {e}"


@mcp.tool()
async def initialize_sonic_pi() -> str:
    """Initialize Sonic Pi - starts it if needed and establishes connection.
    Only call this if Sonic Pi is not running. Use reconnect_sonic_pi() for reconnection.
    
    Returns:
        Connection status message
    """
    if not PSONIC_AVAILABLE:
        return "Error: psonic library not available. Install with: pip install python-sonic"

    # Start Sonic Pi if not running
    if not check_sonic_pi_running():
        if not start_sonic_pi():
            return f"Error: Could not start Sonic Pi. Please start it manually from {SONIC_PI_APP_PATH}"
        
        # Wait for startup
        for _ in range(30):
            time.sleep(1)
            if check_sonic_pi_running():
                time.sleep(9)  # Give it time to write logs
                break
        else:
            return "Error: Sonic Pi started but didn't become ready in time"

    # Connect
    success, message = connect_to_sonic_pi()
    if success:
        return f"✅ {message}. Sonic Pi is ready for music!"
    else:
        return f"Error: {message}. Try restarting Sonic Pi."


@mcp.tool()
async def reconnect_sonic_pi() -> str:
    """Reconnect to Sonic Pi WITHOUT starting or stopping it.
    Use this after chat disconnects or when you need to re-establish connection.
    
    Returns:
        Connection status message
    """
    if not PSONIC_AVAILABLE:
        return "Error: psonic library not available"
    
    if not check_sonic_pi_running():
        return "Error: Sonic Pi not running. Use initialize_sonic_pi() to start it."
    
    success, message = connect_to_sonic_pi()
    if success:
        return f"✅ Reconnected! {message}"
    else:
        return f"Error reconnecting: {message}"


@mcp.tool()
async def play_music(code: str) -> str:
    """Play music using Sonic Pi code.

    Args:
        code: Sonic Pi Ruby code

    Returns:
        A confirmation message
    """
    if not PSONIC_AVAILABLE:
        return "Error: psonic library not available"

    if not check_sonic_pi_running():
        return "Error: Sonic Pi not running. Call initialize_sonic_pi() first."

    if not _psonic_connected:
        success, message = connect_to_sonic_pi()
        if not success:
            return f"Error: Not connected. {message}. Try reconnect_sonic_pi()."

    try:
        run(code)
        return "✅ Music code executed. Check Sonic Pi if you don't hear anything."
    except Exception as e:
        return f"Error playing music: {str(e)}. Try calling reconnect_sonic_pi()."


@mcp.tool()
async def stop_music() -> str:
    """Stop all currently playing Sonic Pi music.

    Returns:
        A confirmation message
    """
    if not PSONIC_AVAILABLE:
        return "Error: psonic library not available"

    if not check_sonic_pi_running():
        return "Sonic Pi not running (music already stopped)"

    try:
        stop()
        return "🛑 All music stopped"
    except Exception as e:
        return f"Error stopping music: {str(e)}"


@mcp.tool()
async def read_shared_state() -> str:
    """Read the current state from shared_state.json.
    This shows the current parameter values for the live mix.
    
    Returns:
        JSON string of current parameters
    """
    try:
        with open(SHARED_STATE_PATH, 'r') as f:
            state = json.load(f)
        return json.dumps(state, indent=2)
    except FileNotFoundError:
        return "Error: shared_state.json not found. Initialize parameters first."
    except Exception as e:
        return f"Error reading state: {e}"


@mcp.tool()
async def change_mix(parameters: dict) -> str:
    """Update parameters in shared_state.json and send them to Sonic Pi.
    
    Args:
        parameters: Dictionary of parameters to update, e.g. {"reverb_mix": 0.8, "hpf_cutoff": 50}
    
    Returns:
        Confirmation message
    """
    if not PSONIC_AVAILABLE:
        return "Error: psonic library not available"
    
    if not check_sonic_pi_running():
        return "Error: Sonic Pi not running"
    
    try:
        # Use parameters directly as a dict
        updates = parameters
        
        # Read current state
        with open(SHARED_STATE_PATH, 'r') as f:
            current_state = json.load(f)
        
        # Update state
        current_state.update(updates)
        
        # Write back to file
        with open(SHARED_STATE_PATH, 'w') as f:
            json.dump(current_state, f, indent=2)
        
        # Send to Sonic Pi using Time State
        commands = []
        for key, value in updates.items():
            # Convert boolean to 1/0 for Sonic Pi
            sp_value = 1 if value is True else (0 if value is False else value)
            commands.append(f"set :{key}, {sp_value}")
        
        code = "\n".join(commands)
        run(code)
        
        updated_params = ", ".join(f"{k}={v}" for k, v in updates.items())
        return f"✅ Updated and sent to Sonic Pi: {updated_params}"
        
    except Exception as e:
        return f"Error updating parameters: {e}"


@mcp.tool()
async def debug_sonic_pi_connection() -> str:
    """Debug Sonic Pi connection parameters and state
    
    Returns:
        Detailed debug information
    """
    debug_info = []
    
    debug_info.append(f"Sonic Pi Running: {check_sonic_pi_running()}")
    debug_info.append(f"psonic Available: {PSONIC_AVAILABLE}")
    debug_info.append(f"psonic Connected: {_psonic_connected}")
    
    ip, gui_port, osc_port, token = parse_sonic_pi_connection_params()
    debug_info.append(f"Parsed IP: {ip}")
    debug_info.append(f"Parsed GUI Port: {gui_port}")
    debug_info.append(f"Parsed OSC Port: {osc_port}")
    debug_info.append(f"Parsed Token: {token}")
    
    daemon_log = get_sonic_pi_log_path()
    debug_info.append(f"Daemon log exists: {daemon_log.exists()}")
    
    # Check shared state file
    state_path = Path(SHARED_STATE_PATH)
    debug_info.append(f"Shared state file exists: {state_path.exists()}")
    
    return "\n".join(debug_info)


@mcp.prompt()
def system_prompt():
    return """You are a Sonic Pi assistant that helps create music with code.

IMPORTANT WORKFLOW:
1. On FIRST connection: Call initialize_sonic_pi() to start and connect
2. After chat disconnect: Call reconnect_sonic_pi() to reconnect WITHOUT disrupting music
3. Use play_music() to execute Sonic Pi code
4. Use stop_music() to stop all sounds
5. Use change_mix() to change live mix parameters

LIVE MIX PARAMETERS:
Use change_mix() with JSON to control live effects. Example:
change_mix('{"reverb_on": true, "reverb_mix": 0.8}')

Available parameters: reverb_on, reverb_mix, reverb_room, reverb_damp, delay_on, 
delay_phase, delay_decay, delay_mix, lpf_on, lpf_cutoff, hpf_on, hpf_cutoff,
distortion_on, distortion_amount, distortion_mix, bitcrusher_on, bitcrusher_bits,
bitcrusher_rate, flanger_on, flanger_depth, flanger_rate, wobble_on, wobble_rate,
wobble_cutoff_min, wobble_cutoff_max, compressor_on, compressor_threshold, compressor_ratio

CHORD REFERENCE:
chord(:C, :major), chord(:C, :m), chord(:C, '7'), chord(:C, :maj7), etc.

COMMON PATTERNS:
- live_loop for repeating patterns
- use_bpm to set tempo
- sleep for timing
- play for notes, play_chord for chords
- sample for drum sounds"""


def main():
    print("🎵 Sonic Pi MCP Server (Improved) starting...")
    
    if check_sonic_pi_running():
        print("✅ Sonic Pi detected running")
    else:
        print("⚠️  Sonic Pi not running - will auto-start when needed")
    
    if PSONIC_AVAILABLE:
        print("✅ psonic library loaded")
    else:
        print("❌ psonic library not available - install with: pip install python-sonic")
    
    # Check shared state file
    if Path(SHARED_STATE_PATH).exists():
        print(f"✅ Shared state file found at {SHARED_STATE_PATH}")
    else:
        print(f"⚠️  Shared state file not found - will create on first use")
    
    print("Ready for MCP connections")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

"""Read-only host probes, called off the scheduling thread."""
import os
import shutil
import subprocess


def probe_host(cfg):
    result = {"clock_sync": "Unknown (not checked on this platform)", "audio_device": "Unverified", "warnings": []}
    if cfg.audio_mode == "system" and not shutil.which("mpv"):
        result["warnings"].append("mpv is not installed or not on the service PATH")
    if os.name != "nt":
        try:
            sync = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                                  capture_output=True, text=True, timeout=3, check=True).stdout.strip()
            result["clock_sync"] = "Synchronized" if sync == "yes" else "Not synchronized"
            if sync != "yes":
                result["warnings"].append("System clock is not NTP synchronized")
        except (OSError, subprocess.SubprocessError):
            result["clock_sync"] = "Unknown; verify with timedatectl"
            result["warnings"].append("Cannot verify NTP synchronization")
        if cfg.audio_mode == "system" and cfg.audio_output == "pulse":
            try:
                sinks = subprocess.run(["pactl", "list", "short", "sinks"], capture_output=True,
                                       text=True, timeout=3, check=True).stdout.strip()
                physical = [line for line in sinks.splitlines() if len(line.split()) > 1
                            and line.split()[1] not in ("auto_null", "dummy")]
                result["audio_device"] = "PulseAudio sinks detected" if physical else "No physical audio sinks detected"
                if not physical:
                    result["warnings"].append("PulseAudio has no output sink")
            except (OSError, subprocess.SubprocessError):
                result["warnings"].append("Cannot inspect the PulseAudio session; verify service audio access")
    return result

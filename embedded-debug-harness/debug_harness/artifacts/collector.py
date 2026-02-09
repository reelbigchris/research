"""Session artifact collection — logs, transcripts, and named captures."""

from __future__ import annotations

import json
from datetime import datetime
from io import TextIOWrapper
from pathlib import Path

from debug_harness.streams.base import StreamLine


class SessionArtifacts:
    """Collects session artifacts into a timestamped directory.

    Produces:
    - session.jsonl: Timestamped event stream (JSON Lines)
    - transcript_<stream>.log: Per-stream raw I/O transcript
    - capture_<name>.txt: Named captures from capture_as directives
    - summary.json: Session summary on close
    """

    def __init__(self, base_dir: str, session_name: str):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._session_dir = Path(base_dir) / f"{session_name}_{ts}"
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._log_file: TextIOWrapper = open(
            self._session_dir / "session.jsonl", "w"
        )
        self._transcripts: dict[str, TextIOWrapper] = {}
        self._captures: dict[str, str] = {}

    @property
    def captures(self) -> dict[str, str]:
        return dict(self._captures)

    @property
    def session_dir(self) -> Path:
        return self._session_dir

    def log_line(self, line: StreamLine) -> None:
        """Log a stream line to the structured event log and per-stream transcript."""
        entry = {
            "ts": line.timestamp.isoformat(),
            "type": "line",
            "stream": line.stream_name,
            "text": line.text,
        }
        self._log_file.write(json.dumps(entry) + "\n")
        self._log_file.flush()

        transcript = self._get_transcript(line.stream_name)
        transcript.write(f"[{line.timestamp:%H:%M:%S.%f}] {line.text}\n")
        transcript.flush()

    def log_event(self, event_type: str, detail: str) -> None:
        """Log a harness event (rule fired, abort, state transition, etc.)."""
        entry = {
            "ts": datetime.now().isoformat(),
            "type": "event",
            "event": event_type,
            "detail": detail,
        }
        self._log_file.write(json.dumps(entry) + "\n")
        self._log_file.flush()

    def save_capture(self, name: str, content: str) -> None:
        """Save a named capture (from capture_as directive)."""
        self._captures[name] = content
        capture_path = self._session_dir / f"capture_{name}.txt"
        capture_path.write_text(content)
        self.log_event("capture", f"{name}: {len(content)} bytes -> {capture_path.name}")

    def save_config(self, config_text: str) -> None:
        """Save the session plan that was used."""
        (self._session_dir / "session_config.yaml").write_text(config_text)

    def _get_transcript(self, stream_name: str) -> TextIOWrapper:
        if stream_name not in self._transcripts:
            path = self._session_dir / f"transcript_{stream_name}.log"
            self._transcripts[stream_name] = open(path, "w")
        return self._transcripts[stream_name]

    def close(self) -> None:
        """Close all file handles and write summary."""
        summary = {
            "session_dir": str(self._session_dir),
            "captures": list(self._captures.keys()),
            "transcripts": [
                p.name for p in self._session_dir.glob("transcript_*")
            ],
        }
        (self._session_dir / "summary.json").write_text(
            json.dumps(summary, indent=2)
        )
        self._log_file.close()
        for f in self._transcripts.values():
            f.close()

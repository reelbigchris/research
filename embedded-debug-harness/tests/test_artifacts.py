"""Tests for session artifact collection."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from debug_harness.artifacts.collector import SessionArtifacts
from debug_harness.streams.base import StreamLine


class TestSessionArtifacts:
    def test_creates_session_directory(self, tmp_path):
        artifacts = SessionArtifacts(str(tmp_path), "test-session")
        assert artifacts.session_dir.exists()
        assert "test-session" in str(artifacts.session_dir)
        artifacts.close()

    def test_log_line(self, tmp_path):
        artifacts = SessionArtifacts(str(tmp_path), "test")
        line = StreamLine(
            text="Step 1: Loading",
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            stream_name="installer",
        )
        artifacts.log_line(line)
        artifacts.close()

        log_path = artifacts.session_dir / "session.jsonl"
        assert log_path.exists()
        with open(log_path) as f:
            entry = json.loads(f.readline())
        assert entry["stream"] == "installer"
        assert entry["text"] == "Step 1: Loading"
        assert entry["type"] == "line"

    def test_log_event(self, tmp_path):
        artifacts = SessionArtifacts(str(tmp_path), "test")
        artifacts.log_event("rule_fired", "set_bp on installer")
        artifacts.close()

        log_path = artifacts.session_dir / "session.jsonl"
        with open(log_path) as f:
            entry = json.loads(f.readline())
        assert entry["event"] == "rule_fired"
        assert entry["detail"] == "set_bp on installer"

    def test_per_stream_transcript(self, tmp_path):
        artifacts = SessionArtifacts(str(tmp_path), "test")
        for i in range(3):
            artifacts.log_line(
                StreamLine(
                    text=f"Line {i}",
                    timestamp=datetime(2024, 1, 15, 10, 30, i),
                    stream_name="installer",
                )
            )
        artifacts.close()

        transcript = artifacts.session_dir / "transcript_installer.log"
        assert transcript.exists()
        content = transcript.read_text()
        assert "Line 0" in content
        assert "Line 2" in content

    def test_save_capture(self, tmp_path):
        artifacts = SessionArtifacts(str(tmp_path), "test")
        artifacts.save_capture("memory_dump", "80004000: 7C 08 02 A6")
        artifacts.close()

        assert "memory_dump" in artifacts.captures
        assert artifacts.captures["memory_dump"] == "80004000: 7C 08 02 A6"

        capture_file = artifacts.session_dir / "capture_memory_dump.txt"
        assert capture_file.exists()
        assert "7C 08 02 A6" in capture_file.read_text()

    def test_save_config(self, tmp_path):
        artifacts = SessionArtifacts(str(tmp_path), "test")
        config_text = "session:\n  name: test\n"
        artifacts.save_config(config_text)
        artifacts.close()

        config_file = artifacts.session_dir / "session_config.yaml"
        assert config_file.exists()
        assert config_file.read_text() == config_text

    def test_summary_on_close(self, tmp_path):
        artifacts = SessionArtifacts(str(tmp_path), "test")
        artifacts.save_capture("cap1", "data1")
        artifacts.save_capture("cap2", "data2")
        artifacts.close()

        summary_file = artifacts.session_dir / "summary.json"
        assert summary_file.exists()
        summary = json.loads(summary_file.read_text())
        assert "cap1" in summary["captures"]
        assert "cap2" in summary["captures"]

    def test_multiple_streams(self, tmp_path):
        artifacts = SessionArtifacts(str(tmp_path), "test")
        artifacts.log_line(
            StreamLine(text="from installer", timestamp=datetime.now(), stream_name="installer")
        )
        artifacts.log_line(
            StreamLine(text="from debug_shell", timestamp=datetime.now(), stream_name="debug_shell")
        )
        artifacts.close()

        assert (artifacts.session_dir / "transcript_installer.log").exists()
        assert (artifacts.session_dir / "transcript_debug_shell.log").exists()

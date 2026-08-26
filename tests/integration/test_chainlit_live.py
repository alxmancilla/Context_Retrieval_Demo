import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.chainlit_live,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_INTEGRATION") != "1",
        reason="set RUN_LIVE_INTEGRATION=1",
    ),
]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_chainlit_starts_and_publishes_expected_settings():
    port = _free_port()
    executable = str(Path(sys.executable).with_name("chainlit"))
    process = subprocess.Popen(
        [executable, "run", "chainlit_app.py", "--headless", "--host", "127.0.0.1",
         "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        base_url = f"http://127.0.0.1:{port}"
        deadline = time.time() + 30
        while time.time() < deadline:
            if process.poll() is not None:
                pytest.fail("Chainlit exited before becoming healthy")
            try:
                with urlopen(f"{base_url}/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.25)
        else:
            pytest.fail("Chainlit did not become healthy within 30 seconds")
        with urlopen(f"{base_url}/ready", timeout=30) as response:
            ready = json.load(response)
        with urlopen(f"{base_url}/project/settings", timeout=3) as response:
            settings = json.load(response)
        assert ready["search_indexes_ready"] == 11
        assert len(settings.get("starters") or []) == 12
        assert settings["ui"]["name"] == "AI Context Platform Assistant"
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
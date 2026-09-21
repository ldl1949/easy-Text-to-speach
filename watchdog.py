"""Watchdog for clipboard_reader.py.

Run periodically by a Task Scheduler task (see watchdog_task_setup.md).
Checks whether clipboard_reader.py is currently running under this
machine's pythonw.exe; if not, relaunches it. Only logs when it takes
action or hits an error -- a "still healthy" heartbeat every few minutes
would just bloat the log file forever with no useful signal.
"""

import logging
import os
import subprocess

import pythoncom
import win32com.client

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(BASE_DIR, "clipboard_reader.py")
PYTHONW = os.path.join(BASE_DIR, ".venv", "Scripts", "pythonw.exe")
LOG_FILE = os.path.join(BASE_DIR, "watchdog.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [Watchdog] %(levelname)s: %(message)s",
)
logger = logging.getLogger("Watchdog")


def is_running():
    """True if any pythonw.exe process is running clipboard_reader.py."""
    pythoncom.CoInitialize()
    try:
        wmi = win32com.client.GetObject("winmgmts:")
        query = "SELECT CommandLine FROM Win32_Process WHERE Name='pythonw.exe'"
        for proc in wmi.ExecQuery(query):
            cmd = proc.CommandLine or ""
            if "clipboard_reader.py" in cmd:
                return True
        return False
    finally:
        pythoncom.CoUninitialize()


def main():
    try:
        if is_running():
            return
    except Exception:
        logger.exception("health check itself failed; skipping this cycle")
        return

    logger.warning("clipboard_reader.py not found running; relaunching")
    try:
        subprocess.Popen([PYTHONW, SCRIPT], cwd=BASE_DIR)
        logger.info("relaunch issued")
    except Exception:
        logger.exception("failed to relaunch clipboard_reader.py")


if __name__ == "__main__":
    main()

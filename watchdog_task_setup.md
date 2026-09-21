# Watchdog scheduled task

`watchdog.py` checks whether `clipboard_reader.py` is currently running
and relaunches it if not. It only writes to `watchdog.log` when it takes
action (down/relaunch/error) -- not on every healthy check -- so the log
doesn't grow forever.

It's driven by a Windows Task Scheduler task, created with:

```
schtasks /Create /TN "ClipboardTTSReaderWatchdog" ^
  /TR "\"<repo>\.venv\Scripts\pythonw.exe\" \"<repo>\watchdog.py\"" ^
  /SC MINUTE /MO 5 /RL LIMITED /F
```

- Runs every 5 minutes, indefinitely (no end date), "Interactive only"
  logon mode -- it needs the interactive desktop session for the tray
  icon and clipboard access, same constraint as clipboard_reader.py
  itself.
- No admin rights needed to create or run it (it's a per-user task,
  not SYSTEM, not "highest privileges").
- Because it re-checks every 5 minutes regardless of whether a fresh
  Windows logon happened, it also covers the "just woke from sleep,
  never actually rebooted" case where the Startup-folder shortcut
  alone would not re-fire.

Useful commands:

```
schtasks /Query /TN "ClipboardTTSReaderWatchdog" /V /FO LIST   # status
schtasks /Run   /TN "ClipboardTTSReaderWatchdog"               # force a check now
schtasks /Change /TN "ClipboardTTSReaderWatchdog" /DISABLE     # pause it
schtasks /Delete /TN "ClipboardTTSReaderWatchdog" /F           # remove it
```

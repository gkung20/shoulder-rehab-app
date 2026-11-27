"""The app's journal (Phase 8.3): %APPDATA%\\Mouvement\\logs\\mouvement.log, 1 MB x 5 files.

`setup()` writes what the console shows (the app's print lines included) to the journal, and
records any error nobody handled, in the main thread or in a worker thread, with its
traceback. The console keeps working as before for development; with the double-click
launcher (no console) the journal is the only place these messages go.

What goes in: the same messages as the console (times, models, camera, errors). No images,
no names, no measurements beyond what the console already prints.
"""
from __future__ import annotations

import io
import logging
import os
import subprocess
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.user_profile import data_dir

LOG_BYTES = 1_000_000   # one file holds 1 MB...
LOG_BACKUPS = 5         # ...and the 5 previous ones are kept
LOGGER = "mouvement"
FORMAT = "%(asctime)s %(levelname)-7s %(threadName)s: %(message)s"


def log_dir():
    return data_dir() / "logs"


def logger():
    return logging.getLogger(LOGGER)


class _Tee(io.TextIOBase):
    """A console stream that also sends each complete line to the journal."""

    def __init__(self, stream, target, level):
        super().__init__()
        self.stream, self.target, self.level, self._pending = stream, target, level, ""
        self.has_console = stream is not None  # False with pythonw (double-click launcher)

    def writable(self):
        return True

    def write(self, text):
        if self.stream is not None:
            try:
                self.stream.write(text)
            except (OSError, ValueError):
                pass
        self._pending += text
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            if line.strip():
                self.target.log(self.level, line.rstrip())
        return len(text)

    def flush(self):
        if self.stream is not None:
            try:
                self.stream.flush()
            except (OSError, ValueError):
                pass

    @property
    def encoding(self):
        return getattr(self.stream, "encoding", "utf-8")

    def isatty(self):
        return bool(self.stream is not None and getattr(self.stream, "isatty", lambda: False)())


class Journal:
    """What setup() changed, so it can be put back (tests, a second start)."""

    def __init__(self, path, handler, stdout, stderr, excepthook, thread_hook):
        self.path, self.handler = path, handler
        self._saved = (stdout, stderr, excepthook, thread_hook)

    def restore(self):
        stdout, stderr, excepthook, thread_hook = self._saved
        sys.stdout, sys.stderr, sys.excepthook, threading.excepthook = stdout, stderr, excepthook, thread_hook
        for name in (LOGGER, LOGGER + ".console"):
            log = logging.getLogger(name)
            for handler in list(log.handlers):
                log.removeHandler(handler)
        self.handler.close()


_current: Journal | None = None


def setup(directory=None, console=True):
    """Start the journal (once); returns it. `directory` defaults to %APPDATA%\\Mouvement\\logs."""
    global _current
    if _current is not None:
        return _current
    folder = Path(directory) if directory is not None else log_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "mouvement.log"
    handler = RotatingFileHandler(path, maxBytes=LOG_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8")
    handler.setFormatter(logging.Formatter(FORMAT))
    original_out, original_err = sys.stdout, sys.stderr

    app = logging.getLogger(LOGGER)
    app.setLevel(logging.INFO)
    app.propagate = False
    app.addHandler(handler)
    if console and original_err is not None:  # the app's own messages also on the console
        stream = logging.StreamHandler(original_err)
        stream.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        app.addHandler(stream)
    # print() lines: already on the console, so only into the file
    printed = logging.getLogger(LOGGER + ".console")
    printed.setLevel(logging.INFO)
    printed.propagate = False
    printed.addHandler(handler)
    sys.stdout = _Tee(original_out, printed, logging.INFO)
    sys.stderr = _Tee(original_err, printed, logging.WARNING)

    excepthook, thread_hook = sys.excepthook, threading.excepthook

    # Errors nobody handled: into the file; the usual hook still prints them on the console.
    def unhandled(kind, error, trace):
        if not issubclass(kind, KeyboardInterrupt):
            printed.critical("Erreur non gérée", exc_info=(kind, error, trace))
        excepthook(kind, error, trace)

    def unhandled_in_thread(args):
        if args.exc_type is not SystemExit:
            name = args.thread.name if args.thread is not None else "?"
            printed.error("Erreur non gérée dans le fil %s", name,
                          exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        thread_hook(args)

    sys.excepthook, threading.excepthook = unhandled, unhandled_in_thread
    _current = Journal(path, handler, original_out, original_err, excepthook, thread_hook)
    return _current


def stop():
    """Put the console and the hooks back (tests)."""
    global _current
    if _current is not None:
        _current.restore()
        _current = None


def open_folder(path):
    """Show a folder in the file explorer; False if that isn't possible here."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606 - the user's own data folder
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except (OSError, AttributeError) as error:
        logger().warning("Dossier du journal impossible à ouvrir : %s", error)
        return False

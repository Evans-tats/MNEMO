"""
Watcher — monitors raw/ for file-system changes and triggers compilation.

Uses watchdog for cross-platform FS events with a configurable debounce timer.
Can also be run in one-shot mode (scan once, compile, exit).

CLI usage:
  kb-ingest watch          # continuous watch mode
  kb-ingest scan           # one-shot scan and compile
  kb-ingest status         # print manifest stats and exit
"""

import logging
import threading
import time
import typer

from typing import Callable
from pathlib import Path
from rich.console import Console

from .manifest import Manifest, ManifestDiff

log = logging.getLogger(__name__)
console = Console()
app = typer.Typer(name='kb-ingest', help="Ingest and compile data from raw/ into the knowledge base.")

class _Debouncer:
    """
    Accumulates FS events and fires a callback after a quiet period.
    Thread-safe: watchdog delivers events from a background thread.
    """
    def __init__(self, callback: Callable[[], None], delay: float):
        self.callback = callback
        self._delay = delay
        self._timer : threading.Timer | None = None
        self._lock = threading.Lock()

    def trigger(self):
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._delay, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self):
        with self._lock:
            self._timer = None
        try:
            self.callback()
        except Exception as e: # noqa: BLE001
            log.error("Error in debounced callback: %s", e, exc_info=True)
    
def _make_watchdog_handler(debouncer: _Debouncer):
    """Build a watchdog EventHandler that feeds the debouncer."""
    try: 
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        log.error("watchdog is required for watch mode. Install with: pip install watchdog")
        raise
    IGNORED = frozenset({"_manifest.json", ".DS_Store"})
    class _WatchdogHandler(FileSystemEventHandler):
        def on_any_event(self, event) -> None:
            if event.is_directory:
                return
            path = Path(getattr(event, "src_path" , ""))
            if path.name in IGNORED or path.suffix in {".tmp", ".swp", ".swx"}:
                return
            log.debug("FS event: %s %s", event.event_type, path)
            debouncer.trigger()
    return _WatchdogHandler()
    
def scan_and_compile(
        raw_dir : Path | None = None, 
        on_diff: Callable[[ManifestDiff], None] | None = None
    ) -> ManifestDiff:
    """
    Scan raw/ for changes, update the manifest, optionally invoke a callback.
    Returns the diff. The actual LLM compilation is triggered via on_diff.
    """
    raw_dir = (raw_dir or cfg.raw_dir).resolve()
    raw_dir.mkdir(parents=True, exist_ok=True)

    manifest = Manifest(raw_dir)
    diff = manifest.scan()
    manifest.save()

    if diff.has_changed:
        console.print(
             f"[bold] Manifest diff:[/bold] {diff.summary()}", style='cyan' 
        )
        if on_diff:
            on_diff(diff)
    else:
        log.debug("No changes detected in raw/.")
    return diff

@app.command("watch")
def cmd_watch(
    raw_dir: Path = typer.Option(None, help="Override raw/ path"),
    debounce: float = typer.Option(None, help="Quiet period in seconds"),
) -> None :
    try:
        from watchdog.observer import Observer
    except ImportError:
        console.print("[red]watchdog not installed. Run pip install watchdog[/red]")
        raise typer.Exit(1)
    
    raw = (raw_dir or cfg.raw).resolve()
    delay = debounce or cfg.debounce_seconds


    console.print(f"[bold green]watching[/bold green] {raw} (debounce{delay}s)")

    def run_and_check_compile():
        diff = scan_and_compile(raw_dir=raw)
        if diff.has_changed:
            console.print(f"[bold green]compilation triggered[/bold green] due to changes in raw/")
    
    _debouncer = _Debouncer(callback=run_and_check_compile, delay=delay)
    _handler = _make_watchdog_handler(_debouncer)

    observer = Observer()
    observer.schedule(_handler, raw, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        Console.print("\n[yellow]Stopping watcher....[/yellow]")
    finally:
        observer.stop()
        observer.join()

@app.command("scan")
def cmd_scan(
    raw_dir: Path = typer.Option(None, help="Override raw/ path"),
    
) -> None:
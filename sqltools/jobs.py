"""Single-job background runner; workers never touch widgets or Qt models."""

from __future__ import annotations

import threading
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


@dataclass(frozen=True, slots=True)
class JobMessage:
    job_id: str
    result: Any = None
    error: str | None = None
    error_type: str | None = None
    traceback_text: str | None = None


class JobContext:
    def __init__(self, job_id: str, cancelled: threading.Event, progress_callback: Callable):
        self.job_id = job_id
        self._cancelled = cancelled
        self._progress_callback = progress_callback

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def check_cancelled(self) -> None:
        if self.cancelled:
            raise JobCancelled("Operation cancelled.")

    def report(self, message: str, value: int = -1) -> None:
        self._progress_callback.emit(self.job_id, message, value)


class JobCancelled(Exception):
    pass


class _Signals(QObject):
    progress = Signal(str, str, int)
    completed = Signal(object)


class _Worker(QRunnable):
    def __init__(self, job_id: str, fn: Callable, cancelled: threading.Event):
        super().__init__()
        self.setAutoDelete(False)
        self.job_id = job_id
        self.fn = fn
        self.cancelled = cancelled
        self.signals = _Signals()

    @Slot()
    def run(self) -> None:
        try:
            context = JobContext(self.job_id, self.cancelled, self.signals.progress)
            result = self.fn(context)
            message = JobMessage(self.job_id, result=result)
        except JobCancelled as error:
            message = JobMessage(self.job_id, error=str(error), error_type=type(error).__name__)
        except Exception as error:  # Worker boundary: send traceback to the application log.
            message = JobMessage(
                self.job_id,
                error=str(error) or type(error).__name__,
                error_type=type(error).__name__,
                traceback_text=traceback.format_exc(),
            )
        self.signals.completed.emit(message)


class JobManager(QObject):
    """Runs at most one task and holds every worker until its queued result arrives."""

    started = Signal(str, str)
    progress = Signal(str, str, int)
    completed = Signal(object)
    busy_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self._workers: dict[str, tuple[_Worker, threading.Event]] = {}

    @property
    def busy(self) -> bool:
        return bool(self._workers)

    def submit(self, name: str, fn: Callable[[JobContext], Any]) -> str:
        if self.busy:
            raise RuntimeError("Another operation is already running.")
        job_id = uuid.uuid4().hex
        cancelled = threading.Event()
        worker = _Worker(job_id, fn, cancelled)
        worker.signals.progress.connect(self.progress)
        worker.signals.completed.connect(self._on_completed)
        self._workers[job_id] = (worker, cancelled)
        self.started.emit(job_id, name)
        self.busy_changed.emit(True)
        self.pool.start(worker)
        return job_id

    def cancel(self, job_id: str | None = None) -> None:
        for current_id, (_, event) in self._workers.items():
            if job_id is None or current_id == job_id:
                event.set()

    @Slot(object)
    def _on_completed(self, message: JobMessage) -> None:
        self._workers.pop(message.job_id, None)
        self.completed.emit(message)
        self.busy_changed.emit(self.busy)

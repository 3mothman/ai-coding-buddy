"""Bounded background work with revision tokens to discard stale results."""
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from .analysis import TutorError

class WorkerSignals(QObject):
    finished = Signal(int, object, str)

class Worker(QRunnable):
    def __init__(self, token, provider, snapshot):
        super().__init__()
        self.token, self.provider, self.snapshot = token, provider, snapshot
        self.signals = WorkerSignals()

    def run(self):
        try:
            feedback, error = self.provider.analyze(self.snapshot), ""
        except TutorError as failure:
            feedback, error = None, str(failure)
        except Exception:
            feedback, error = None, "Analysis failed. Check the provider settings or use demo mode."
        self.signals.finished.emit(self.token, feedback, error)

class TutorController(QObject):
    result = Signal(object)
    failure = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.revision = 0
        self.active = None
        self.pending = None
        self.stopped = False

    def invalidate(self):
        self.revision += 1
        self.pending = None

    def request(self, provider, snapshot):
        if self.stopped:
            return
        self.revision += 1
        job = (self.revision, provider, snapshot)
        if self.active is not None:
            self.pending = job
        else:
            self._start(job)

    def _start(self, job):
        self.active = Worker(*job)
        self.active.signals.finished.connect(self._finished)
        self.busy_changed.emit(True)
        QThreadPool.globalInstance().start(self.active)

    @Slot(int, object, str)
    def _finished(self, token, feedback, error):
        self.active = None
        if not self.stopped and token == self.revision:
            if error:
                self.failure.emit(error)
            else:
                self.result.emit(feedback)
        pending, self.pending = self.pending, None
        if pending is not None and not self.stopped:
            self._start(pending)
        else:
            self.busy_changed.emit(False)

    def shutdown(self):
        self.stopped = True
        self.invalidate()

"""One authority for accepted learning state, speech timing and model results."""
from collections import deque
from dataclasses import dataclass, field, replace
import time

from PySide6.QtCore import QObject, Signal
from .controller import TutorController


@dataclass
class AssistancePolicy:
    inactivity: float = 25.0
    cooldown: float = 45.0
    speech_settle: float = 2.0
    last_hint: float = -1e9
    last_voice_activity: float = -1e9
    speaking: bool = False
    listening: bool = False
    last_auto_revision: int = -1
    last_analysis: float = -1e9
    messages: deque = field(default_factory=lambda: deque(maxlen=12))

    def can_analyze(self, now, last_edit, revision, minimum_idle=None):
        return (not self.speaking and not self.listening
                and now - self.last_voice_activity >= self.speech_settle
                and now - last_edit >= (self.inactivity if minimum_idle is None else minimum_idle)
                and now - self.last_analysis >= 10
                and now - self.last_hint >= self.cooldown
                and revision != self.last_auto_revision)

    def should_deliver(self, feedback, now, automatic=False):
        if feedback.action == "stay_silent" or not feedback.message:
            return False
        if automatic:
            confidence = (feedback.structured or {}).get("analysis", {}).get("confidence", 0.0)
            if (self.speaking or self.listening or now - self.last_voice_activity < self.speech_settle
                    or now - self.last_hint < self.cooldown or confidence < 0.75
                    or feedback.message in self.messages):
                return False
        return True


@dataclass
class LearningMemory:
    reference: dict | None = None
    completed: list[str] = field(default_factory=list)
    objective: str = ""
    summary: str = ""
    conversation: deque = field(default_factory=lambda: deque(maxlen=12))
    hints: deque = field(default_factory=lambda: deque(maxlen=12))
    mistakes: dict = field(default_factory=dict)

    def remember(self, role, text):
        if text.strip():
            item = {"role": role, "text": text[:1500]}
            if not self.conversation or self.conversation[-1] != item:
                self.conversation.append(item)


class LearningOrchestrator(QObject):
    result = Signal(object)
    failure = Signal(str)
    busy_changed = Signal(bool)
    state_changed = Signal()

    def __init__(self, parent=None, clock=time.monotonic):
        super().__init__(parent)
        self.clock = clock
        self.worker = TutorController(self)
        self.worker.result.connect(self._accept)
        self.worker.failure.connect(self.failure)
        self.worker.busy_changed.connect(self.busy_changed)
        self.policy = AssistancePolicy()
        self.memory = LearningMemory()
        self.revision = 0
        self.last_edit = clock()
        self.code = ""
        self.snapshot = None
        self.last_feedback = None

    def reset(self):
        self.invalidate()
        self.memory = LearningMemory()
        self.policy = AssistancePolicy(self.policy.inactivity, self.policy.cooldown)
        self.last_feedback = None
        self.snapshot = None

    def invalidate(self):
        self.revision += 1
        self.worker.invalidate()

    def edited(self, code):
        self.invalidate()
        self.code = code
        self.last_edit = self.clock()
        # Keep previous evidence as history. The next model call must re-evaluate
        # it against current code, and can retract objectives that were removed.

    def voice_activity(self, speaking=None, listening=None):
        if speaking is not None:
            self.policy.speaking = speaking
        if listening is not None:
            self.policy.listening = listening
        self.policy.last_voice_activity = self.clock()

    def request(self, provider, snap):
        if snap.answer:
            self.memory.remember("user", snap.answer)
        snap = replace(snap, reference_analysis=self.memory.reference,
                       completed_objectives=tuple(self.memory.completed),
                       current_objective=self.memory.objective,
                       session_summary=self.memory.summary,
                       conversation=tuple(self.memory.conversation), revision=self.revision,
                       repeated_mistakes=tuple(self.memory.mistakes.items()))
        self.snapshot = snap
        if snap.reason == "auto":
            self.policy.last_auto_revision = self.revision
            self.policy.last_analysis = self.clock()
        self.worker.request(provider, snap)

    def _accept(self, feedback):
        snap = self.snapshot
        if snap is None or snap.revision != self.revision:
            return
        structured = feedback.structured
        if structured:
            if snap.reason == "prepare":
                self.memory.reference = structured["reference"]
            progress = structured["student_progress"]
            self.memory.completed = progress["completed"]
            self.memory.objective = progress["current_objective"]
            self.memory.summary = structured["memory_summary"]
            issue = structured["analysis"]["issue"]
            if issue:
                self.memory.mistakes[issue] = self.memory.mistakes.get(issue, 0) + 1
                if len(self.memory.mistakes) > 30:
                    del self.memory.mistakes[next(iter(self.memory.mistakes))]
        self.last_feedback = feedback
        self.state_changed.emit()
        automatic = snap.reason == "auto"
        if not self.policy.should_deliver(feedback, self.clock(), automatic):
            # The GUI still needs the initial prepared state, even if no introduction.
            if snap.reason == "prepare":
                self.result.emit(feedback)
            return
        self.policy.last_hint = self.clock()
        self.policy.messages.append(feedback.message)
        self.memory.hints.append(feedback.message)
        self.memory.remember("assistant", feedback.message)
        self.result.emit(feedback)

    def shutdown(self):
        self.worker.shutdown()

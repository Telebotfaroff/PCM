"""Job state machine shared by bot, worker, and persistence layers."""

from enum import StrEnum


class JobState(StrEnum):
    RECEIVED = "received"
    RESOLVING = "resolving"
    AWAITING_SELECTION = "awaiting_selection"
    QUEUED = "queued"
    WAITING_FOR_WORKER = "waiting_for_worker"
    DOWNLOADING = "downloading"
    VALIDATING = "validating"
    UPLOADING = "uploading"
    PAUSED = "paused"
    RETRY_WAIT = "retry_wait"
    COMPLETED = "completed"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RECOVERY_NEEDED = "recovery_needed"


_ALLOWED: dict[JobState, set[JobState]] = {
    JobState.RECEIVED: {JobState.RESOLVING, JobState.CANCELLED, JobState.FAILED},
    JobState.RESOLVING: {
        JobState.AWAITING_SELECTION, JobState.QUEUED, JobState.RETRY_WAIT,
        JobState.FAILED, JobState.CANCELLED,
    },
    JobState.AWAITING_SELECTION: {JobState.QUEUED, JobState.CANCELLED, JobState.FAILED},
    JobState.QUEUED: {
        JobState.WAITING_FOR_WORKER, JobState.DOWNLOADING, JobState.CANCELLED,
        JobState.PAUSED, JobState.FAILED,
    },
    JobState.WAITING_FOR_WORKER: {
        JobState.QUEUED, JobState.DOWNLOADING, JobState.CANCELLED,
        JobState.PAUSED, JobState.RECOVERY_NEEDED,
    },
    JobState.DOWNLOADING: {
        JobState.VALIDATING, JobState.PAUSED, JobState.RETRY_WAIT,
        JobState.FAILED, JobState.CANCELLED, JobState.RECOVERY_NEEDED,
    },
    JobState.VALIDATING: {
        JobState.UPLOADING, JobState.RETRY_WAIT, JobState.FAILED,
        JobState.CANCELLED, JobState.RECOVERY_NEEDED,
    },
    JobState.UPLOADING: {
        JobState.COMPLETED, JobState.PARTIAL_SUCCESS, JobState.PAUSED,
        JobState.RETRY_WAIT, JobState.FAILED, JobState.CANCELLED,
        JobState.RECOVERY_NEEDED,
    },
    JobState.PAUSED: {
        JobState.QUEUED, JobState.DOWNLOADING, JobState.UPLOADING,
        JobState.CANCELLED, JobState.FAILED,
    },
    JobState.RETRY_WAIT: {
        JobState.QUEUED, JobState.DOWNLOADING, JobState.UPLOADING,
        JobState.CANCELLED, JobState.FAILED, JobState.RECOVERY_NEEDED,
    },
    JobState.RECOVERY_NEEDED: {
        JobState.QUEUED, JobState.RETRY_WAIT, JobState.COMPLETED,
        JobState.PARTIAL_SUCCESS, JobState.FAILED, JobState.CANCELLED,
    },
    JobState.PARTIAL_SUCCESS: {JobState.UPLOADING, JobState.COMPLETED, JobState.FAILED},
    JobState.COMPLETED: set(),
    JobState.FAILED: {JobState.QUEUED},
    JobState.CANCELLED: {JobState.QUEUED},
}


def can_transition(current: JobState, target: JobState) -> bool:
    """Return whether a state transition is allowed."""
    return target in _ALLOWED[current]


def transition(current: JobState, target: JobState) -> JobState:
    """Validate and return the target state; persistence must save it atomically."""
    if not can_transition(current, target):
        raise ValueError(f"Invalid job transition: {current.value} -> {target.value}")
    return target

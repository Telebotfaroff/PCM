import pytest

from pcm.jobs.states import JobState, can_transition, transition


def test_queued_job_can_start_download():
    assert transition(JobState.QUEUED, JobState.DOWNLOADING) is JobState.DOWNLOADING


def test_completed_job_is_terminal():
    assert not can_transition(JobState.COMPLETED, JobState.QUEUED)


def test_invalid_transition_raises():
    with pytest.raises(ValueError, match="Invalid job transition"):
        transition(JobState.RECEIVED, JobState.UPLOADING)


def test_failed_job_can_be_retried():
    assert can_transition(JobState.FAILED, JobState.QUEUED)

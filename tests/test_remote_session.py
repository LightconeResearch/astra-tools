"""Tests for RemoteSession with mocked SSHBackend."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from asp.remote.client import ClusterClient, JobState
from asp.remote.jobs import JobHandle, JobRegistry
from asp.remote.session import RemoteSession


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal ASP project structure with remote.yaml."""
    # asp.yaml
    (tmp_path / "asp.yaml").write_text("version: '1.0'\nanalysis:\n  name: test\n")
    # remote.yaml
    (tmp_path / "remote.yaml").write_text(
        "target: testcluster\n"
        "clusters:\n"
        "  testcluster:\n"
        "    backend: ssh\n"
        "    ssh_host: login.example.com\n"
        "    ssh_user: testuser\n"
        "    workdir: /scratch/testuser/project\n"
    )
    # universes/
    universes = tmp_path / "universes"
    universes.mkdir()
    (universes / "baseline.yaml").write_text("id: baseline\n")
    # steps/
    steps = tmp_path / "steps"
    steps.mkdir()
    (steps / "main.py").write_text("print('hello')\n")
    # workflows/ (empty)
    (tmp_path / "workflows").mkdir()
    # Things that should NOT be pushed
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "baseline").mkdir()
    (tmp_path / "results" / "baseline" / "out.csv").write_text("1,2,3\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / "__pycache__").mkdir()
    return tmp_path


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock ClusterClient."""
    client = MagicMock(spec=ClusterClient)
    client.upload = MagicMock()
    client.download = MagicMock()
    client.exec_command = MagicMock(return_value=("", "", 0))
    client.submit_batch = MagicMock(return_value="12345")
    client.job_status = MagicMock(return_value=JobState(JobState.PENDING))
    return client


@pytest.fixture
def session(project_dir: Path, mock_client: MagicMock) -> RemoteSession:
    """Create a RemoteSession with mocked client."""
    s = RemoteSession(project_dir)
    s._client = mock_client
    return s


# ---------------------------------------------------------------------------
# Tests: push_project
# ---------------------------------------------------------------------------

class TestPushProject:
    def test_default_push_includes_correct_files(self, session: RemoteSession, mock_client: MagicMock) -> None:
        pushed = session.push_project()

        # Should include asp.yaml, remote.yaml, universes/, steps/, workflows/
        assert "asp.yaml" in pushed
        assert "remote.yaml" in pushed
        assert "universes/" in pushed
        assert "steps/" in pushed
        assert "workflows/" in pushed

        # Verify upload was called for each
        upload_calls = mock_client.upload.call_args_list
        remote_paths = [c[0][1] for c in upload_calls]

        assert any("asp.yaml" in p for p in remote_paths)
        assert any("universes" in p for p in remote_paths)
        assert any("steps" in p for p in remote_paths)

    def test_default_push_excludes_results_and_git(self, session: RemoteSession, mock_client: MagicMock) -> None:
        pushed = session.push_project()

        # Should NOT include results/, .git/, __pycache__/
        assert not any("results" in item for item in pushed)
        assert not any(".git" in item for item in pushed)
        assert not any("__pycache__" in item for item in pushed)

    def test_push_specific_paths(self, session: RemoteSession, mock_client: MagicMock) -> None:
        pushed = session.push_project(paths=["asp.yaml", "steps"])

        assert pushed == ["asp.yaml", "steps"]
        assert mock_client.upload.call_count == 2

    def test_push_skips_nonexistent(self, session: RemoteSession, mock_client: MagicMock) -> None:
        pushed = session.push_project(paths=["asp.yaml", "nonexistent.txt"])

        assert "asp.yaml" in pushed
        assert "nonexistent.txt" not in pushed

    def test_push_raises_without_workdir(self, session: RemoteSession) -> None:
        # Override config to have no workdir
        session._config = {"target": "testcluster", "clusters": {"testcluster": {}}}

        with pytest.raises(ValueError, match="No workdir"):
            session.push_project()


# ---------------------------------------------------------------------------
# Tests: exec
# ---------------------------------------------------------------------------

class TestExec:
    def test_exec_prepends_cd(self, session: RemoteSession, mock_client: MagicMock) -> None:
        mock_client.exec_command.return_value = ("output", "", 0)

        stdout, stderr, code = session.exec("ls -la")

        mock_client.exec_command.assert_called_once_with(
            "cd /scratch/testuser/project && ls -la"
        )
        assert stdout == "output"
        assert code == 0

    def test_exec_custom_cwd(self, session: RemoteSession, mock_client: MagicMock) -> None:
        session.exec("pwd", cwd="/tmp/other")

        mock_client.exec_command.assert_called_once_with(
            "cd /tmp/other && pwd"
        )

    def test_exec_returns_exit_code(self, session: RemoteSession, mock_client: MagicMock) -> None:
        mock_client.exec_command.return_value = ("", "error", 1)

        _, stderr, code = session.exec("false")

        assert stderr == "error"
        assert code == 1


# ---------------------------------------------------------------------------
# Tests: poll_jobs
# ---------------------------------------------------------------------------

class TestPollJobs:
    def test_poll_detects_status_change(self, session: RemoteSession, mock_client: MagicMock) -> None:
        # Add a PENDING job to the registry
        job = JobHandle.create(
            cluster="testcluster",
            universe_id="baseline",
            remote_job_id="99999",
            workdir="/scratch/testuser/project",
        )
        session.registry.add(job)

        # Mock: job has transitioned to RUNNING
        mock_client.job_status.return_value = JobState(JobState.RUNNING)

        changes = session.poll_jobs()

        assert len(changes) == 1
        changed_job, old, new = changes[0]
        assert old == "PENDING"
        assert new == "RUNNING"
        assert changed_job.job_id == job.job_id

    def test_poll_skips_terminal_jobs(self, session: RemoteSession, mock_client: MagicMock) -> None:
        # Add a COMPLETED job
        job = JobHandle.create(
            cluster="testcluster",
            universe_id="baseline",
            remote_job_id="88888",
            workdir="/scratch/testuser/project",
        )
        job.status = "COMPLETED"
        session.registry.add(job)

        changes = session.poll_jobs()

        # Should not poll completed jobs
        assert len(changes) == 0
        mock_client.job_status.assert_not_called()

    def test_poll_no_change(self, session: RemoteSession, mock_client: MagicMock) -> None:
        job = JobHandle.create(
            cluster="testcluster",
            universe_id="baseline",
            remote_job_id="77777",
            workdir="/scratch/testuser/project",
        )
        session.registry.add(job)

        # Status hasn't changed
        mock_client.job_status.return_value = JobState(JobState.PENDING)

        changes = session.poll_jobs()
        assert len(changes) == 0

    def test_poll_updates_registry(self, session: RemoteSession, mock_client: MagicMock) -> None:
        job = JobHandle.create(
            cluster="testcluster",
            universe_id="baseline",
            remote_job_id="66666",
            workdir="/scratch/testuser/project",
        )
        session.registry.add(job)
        mock_client.job_status.return_value = JobState(JobState.COMPLETED)

        session.poll_jobs()

        # Verify the registry was updated
        updated = session.registry.get(job.job_id)
        assert updated is not None
        assert updated.status == "COMPLETED"


# ---------------------------------------------------------------------------
# Tests: pull_results
# ---------------------------------------------------------------------------

class TestPullResults:
    def test_pull_by_universe(self, session: RemoteSession, mock_client: MagicMock) -> None:
        local_path = session.pull_results(universe_id="baseline")

        expected_local = session._project_dir / "results" / "baseline"
        assert local_path == expected_local
        mock_client.download.assert_called_once_with(
            "/scratch/testuser/project/results/baseline",
            expected_local,
        )

    def test_pull_by_job_id(self, session: RemoteSession, mock_client: MagicMock) -> None:
        job = JobHandle.create(
            cluster="testcluster",
            universe_id="experiment1",
            remote_job_id="55555",
            workdir="/scratch/testuser/project",
        )
        session.registry.add(job)

        local_path = session.pull_results(job_id=job.job_id)

        expected_local = session._project_dir / "results" / "experiment1"
        assert local_path == expected_local

    def test_pull_defaults_to_default_universe(self, session: RemoteSession, mock_client: MagicMock) -> None:
        session.pull_results()

        mock_client.download.assert_called_once()
        remote_path = mock_client.download.call_args[0][0]
        assert remote_path.endswith("/results/default")

    def test_pull_unknown_job_raises(self, session: RemoteSession) -> None:
        with pytest.raises(ValueError, match="not found"):
            session.pull_results(job_id="nonexistent")


# ---------------------------------------------------------------------------
# Tests: submit
# ---------------------------------------------------------------------------

class TestSubmit:
    def test_submit_pushes_then_submits(self, session: RemoteSession, mock_client: MagicMock) -> None:
        handle = session.submit(universe_id="baseline")

        # Should have pushed files (upload called multiple times)
        assert mock_client.upload.call_count > 0

        # Should have submitted
        mock_client.submit_batch.assert_called_once_with(
            "/scratch/testuser/project/job.sh"
        )

        # Should return a handle
        assert handle.remote_job_id == "12345"
        assert handle.universe_id == "baseline"
        assert handle.status == "PENDING"

    def test_submit_writes_script_content(self, session: RemoteSession, mock_client: MagicMock) -> None:
        session.submit(script_content="#!/bin/bash\necho hello", universe_id="baseline")

        # Should have written the script via write_text
        mock_client.write_text.assert_called_once_with(
            "/scratch/testuser/project/job.sh", "#!/bin/bash\necho hello"
        )
        # Should have made it executable
        exec_calls = [c[0][0] for c in mock_client.exec_command.call_args_list]
        assert any("chmod +x" in c for c in exec_calls)

    def test_submit_adds_to_registry(self, session: RemoteSession, mock_client: MagicMock) -> None:
        handle = session.submit(universe_id="test_universe")

        jobs = session.registry.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].job_id == handle.job_id
        assert jobs[0].remote_job_id == "12345"


# ---------------------------------------------------------------------------
# Tests: properties
# ---------------------------------------------------------------------------

class TestProperties:
    def test_target(self, session: RemoteSession) -> None:
        assert session.target == "testcluster"

    def test_remote_workdir(self, session: RemoteSession) -> None:
        assert session.remote_workdir == "/scratch/testuser/project"

    def test_cluster_config(self, session: RemoteSession) -> None:
        cfg = session.cluster_config
        assert cfg["ssh_host"] == "login.example.com"
        assert cfg["ssh_user"] == "testuser"

    def test_close_is_safe(self, session: RemoteSession) -> None:
        # Should not raise even if called multiple times
        session.close()
        session.close()

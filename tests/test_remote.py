"""Tests for the asp.remote package — no credentials needed."""

from __future__ import annotations

from pathlib import Path

import pytest

from asp.remote.client import ClusterClient, JobState, SSHBackend, load_remote_config
from asp.remote.jobs import JobHandle, JobRegistry


# ---------------------------------------------------------------------------
# jobs tests
# ---------------------------------------------------------------------------


class TestJobHandle:
    def test_create(self):
        job = JobHandle.create(
            cluster="perlmutter",
            universe_id="baseline",
            remote_job_id="12345",
            workdir="/pscratch/test",
        )
        assert job.cluster == "perlmutter"
        assert job.universe_id == "baseline"
        assert job.remote_job_id == "12345"
        assert job.status == "PENDING"
        assert len(job.job_id) == 12

    def test_roundtrip(self):
        job = JobHandle.create(
            cluster="perlmutter",
            universe_id="baseline",
            remote_job_id="12345",
            workdir="/pscratch/test",
        )
        d = job.to_dict()
        restored = JobHandle.from_dict(d)
        assert restored.job_id == job.job_id
        assert restored.cluster == job.cluster
        assert restored.status == job.status


class TestJobRegistry:
    def test_add_and_list(self, tmp_path: Path):
        registry = JobRegistry(tmp_path)
        job = JobHandle.create(
            cluster="perlmutter",
            universe_id="baseline",
            remote_job_id="12345",
            workdir="/pscratch/test",
        )
        registry.add(job)

        jobs = registry.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].job_id == job.job_id

    def test_get(self, tmp_path: Path):
        registry = JobRegistry(tmp_path)
        job = JobHandle.create(
            cluster="perlmutter",
            universe_id="baseline",
            remote_job_id="12345",
            workdir="/pscratch/test",
        )
        registry.add(job)

        found = registry.get(job.job_id)
        assert found is not None
        assert found.remote_job_id == "12345"

    def test_get_not_found(self, tmp_path: Path):
        registry = JobRegistry(tmp_path)
        assert registry.get("nonexistent") is None

    def test_update_status(self, tmp_path: Path):
        registry = JobRegistry(tmp_path)
        job = JobHandle.create(
            cluster="perlmutter",
            universe_id="baseline",
            remote_job_id="12345",
            workdir="/pscratch/test",
        )
        registry.add(job)
        registry.update_status(job.job_id, "COMPLETED")

        updated = registry.get(job.job_id)
        assert updated is not None
        assert updated.status == "COMPLETED"

    def test_remove(self, tmp_path: Path):
        registry = JobRegistry(tmp_path)
        job = JobHandle.create(
            cluster="perlmutter",
            universe_id="baseline",
            remote_job_id="12345",
            workdir="/pscratch/test",
        )
        registry.add(job)
        assert registry.remove(job.job_id) is True
        assert registry.list_jobs() == []

    def test_persistence(self, tmp_path: Path):
        """Jobs persist across registry instances."""
        job = JobHandle.create(
            cluster="perlmutter",
            universe_id="baseline",
            remote_job_id="12345",
            workdir="/pscratch/test",
        )
        JobRegistry(tmp_path).add(job)

        # New instance should see the job
        jobs = JobRegistry(tmp_path).list_jobs()
        assert len(jobs) == 1


# ---------------------------------------------------------------------------
# client tests
# ---------------------------------------------------------------------------


class TestJobState:
    def test_terminal_states(self):
        assert JobState(JobState.COMPLETED).is_terminal
        assert JobState(JobState.FAILED).is_terminal
        assert not JobState(JobState.PENDING).is_terminal
        assert not JobState(JobState.RUNNING).is_terminal

    def test_str(self):
        assert str(JobState(JobState.RUNNING)) == "RUNNING"


class TestLoadRemoteConfig:
    def test_missing_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_remote_config(tmp_path)

    def test_load(self, tmp_path: Path):
        config = {
            "target": "perlmutter",
            "clusters": {
                "perlmutter": {
                    "backend": "ssh",
                    "ssh_host": "perlmutter.nersc.gov",
                    "ssh_user": "testuser",
                },
            },
        }
        import yaml

        (tmp_path / "remote.yaml").write_text(yaml.safe_dump(config))
        loaded = load_remote_config(tmp_path)
        assert loaded["target"] == "perlmutter"
        assert loaded["clusters"]["perlmutter"]["backend"] == "ssh"


class TestGetClient:
    def test_unknown_target(self, tmp_path: Path):
        from asp.remote.client import get_client

        config = {"target": "unknown", "clusters": {}}
        import yaml

        (tmp_path / "remote.yaml").write_text(yaml.safe_dump(config))
        with pytest.raises(ValueError, match="not found"):
            get_client(tmp_path)

    def test_returns_ssh_backend(self, tmp_path: Path):
        from asp.remote.client import get_client

        config = {
            "target": "perlmutter",
            "clusters": {
                "perlmutter": {
                    "backend": "ssh",
                    "ssh_host": "perlmutter.nersc.gov",
                    "ssh_user": "testuser",
                },
            },
        }
        import yaml

        (tmp_path / "remote.yaml").write_text(yaml.safe_dump(config))
        client = get_client(tmp_path)
        assert isinstance(client, SSHBackend)
        assert client.config["ssh_host"] == "perlmutter.nersc.gov"

    def test_globus_backend_raises(self, tmp_path: Path):
        from asp.remote.client import get_client

        config = {
            "target": "perlmutter",
            "clusters": {
                "perlmutter": {
                    "backend": "globus",
                    "endpoint_id": "abc-def-123",
                },
            },
        }
        import yaml

        (tmp_path / "remote.yaml").write_text(yaml.safe_dump(config))
        with pytest.raises(ValueError, match="Globus backend has been removed"):
            get_client(tmp_path)

    def test_default_backend_is_ssh(self, tmp_path: Path):
        from asp.remote.client import get_client

        config = {
            "target": "perlmutter",
            "clusters": {
                "perlmutter": {
                    "ssh_host": "perlmutter.nersc.gov",
                    "ssh_user": "testuser",
                },
            },
        }
        import yaml

        (tmp_path / "remote.yaml").write_text(yaml.safe_dump(config))
        client = get_client(tmp_path)
        assert isinstance(client, SSHBackend)

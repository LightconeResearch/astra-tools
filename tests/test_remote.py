"""Tests for the asp.remote package — no credentials needed."""

from __future__ import annotations

from pathlib import Path

import pytest

from asp.remote.client import ClusterClient, JobState, SSHBackend, load_remote_config
from asp.remote.jobs import JobHandle, JobRegistry
from asp.remote.script_gen import generate_batch_script


# ---------------------------------------------------------------------------
# script_gen tests
# ---------------------------------------------------------------------------


class TestBatchScriptGeneration:
    """Test that batch script generation produces correct output."""

    @pytest.fixture()
    def sample_analysis(self) -> dict:
        return {
            "analysis": {
                "name": "Test Analysis",
                "inputs": [
                    {
                        "id": "primary_data",
                        "type": "data",
                        "source": "/path/to/data.csv",
                    }
                ],
                "outputs": [
                    {"id": "main_result", "type": "metric", "path": "result.json"},
                ],
            },
            "chunks": {
                "main": {
                    "decisions": {
                        "method": {
                            "label": "Method",
                            "type": "method",
                            "default": "linear",
                            "options": {
                                "linear": {"label": "Linear", "value": "linear"},
                                "nonlinear": {"label": "Nonlinear", "value": "nonlinear"},
                            },
                        },
                        "threshold": {
                            "label": "Threshold",
                            "type": "parameter",
                            "default": "high",
                            "options": {
                                "high": {"label": "High", "value": 0.9},
                                "low": {"label": "Low", "value": 0.5},
                            },
                        },
                    }
                }
            },
        }

    @pytest.fixture()
    def sample_universe(self) -> dict:
        return {
            "id": "baseline",
            "chunks": {
                "main": {
                    "method": "linear",
                    "threshold": "high",
                }
            },
        }

    @pytest.fixture()
    def sample_cluster_config(self) -> dict:
        return {
            "account": "m1234",
            "workdir": "/pscratch/sd/u/user/asp",
            "python": "python3",
            "slurm": {
                "qos": "regular",
                "constraint": "cpu",
                "time": "00:30:00",
                "nodes": 1,
            },
        }

    def test_script_has_shebang(self, sample_analysis, sample_universe, sample_cluster_config):
        script = generate_batch_script(
            sample_analysis, sample_universe, sample_cluster_config,
            "/pscratch/sd/u/user/asp/jobs/baseline",
        )
        assert script.startswith("#!/bin/bash")

    def test_script_has_sbatch_directives(self, sample_analysis, sample_universe, sample_cluster_config):
        script = generate_batch_script(
            sample_analysis, sample_universe, sample_cluster_config,
            "/pscratch/sd/u/user/asp/jobs/baseline",
        )
        assert "#SBATCH --job-name=asp-baseline" in script
        assert "#SBATCH --account=m1234" in script
        assert "#SBATCH --qos=regular" in script
        assert "#SBATCH --constraint=cpu" in script
        assert "#SBATCH --time=00:30:00" in script
        assert "#SBATCH --nodes=1" in script

    def test_script_has_decision_env_vars(self, sample_analysis, sample_universe, sample_cluster_config):
        script = generate_batch_script(
            sample_analysis, sample_universe, sample_cluster_config,
            "/pscratch/sd/u/user/asp/jobs/baseline",
        )
        assert "export ASP_DECISION_METHOD=linear" in script
        assert "export ASP_DECISION_THRESHOLD=0.9" in script

    def test_script_has_input_env_vars(self, sample_analysis, sample_universe, sample_cluster_config):
        script = generate_batch_script(
            sample_analysis, sample_universe, sample_cluster_config,
            "/pscratch/sd/u/user/asp/jobs/baseline",
        )
        assert "export ASP_INPUT_PRIMARY_DATA=/path/to/data.csv" in script

    def test_script_has_results_dir(self, sample_analysis, sample_universe, sample_cluster_config):
        script = generate_batch_script(
            sample_analysis, sample_universe, sample_cluster_config,
            "/pscratch/sd/u/user/asp/jobs/baseline",
        )
        assert "export ASP_RESULTS_DIR=" in script
        assert "/pscratch/sd/u/user/asp/jobs/baseline/results" in script

    def test_script_runs_main_py(self, sample_analysis, sample_universe, sample_cluster_config):
        script = generate_batch_script(
            sample_analysis, sample_universe, sample_cluster_config,
            "/pscratch/sd/u/user/asp/jobs/baseline",
        )
        assert "python3 steps/main.py" in script

    def test_dict_value_flattening(self, sample_cluster_config):
        """Test that dict-typed option values are flattened correctly."""
        analysis = {
            "analysis": {"name": "Test", "inputs": [], "outputs": []},
            "chunks": {
                "main": {
                    "decisions": {
                        "grid": {
                            "label": "Grid",
                            "type": "parameter",
                            "default": "coarse",
                            "options": {
                                "coarse": {
                                    "label": "Coarse",
                                    "value": {"nx": 64, "ny": 64},
                                },
                            },
                        },
                    },
                },
            },
        }
        universe = {"id": "test", "chunks": {"main": {"grid": "coarse"}}}
        script = generate_batch_script(analysis, universe, sample_cluster_config, "/tmp/job")
        assert "export ASP_DECISION_GRID_NX=64" in script
        assert "export ASP_DECISION_GRID_NY=64" in script


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

        (tmp_path / "asp-remote.yaml").write_text(yaml.safe_dump(config))
        loaded = load_remote_config(tmp_path)
        assert loaded["target"] == "perlmutter"
        assert loaded["clusters"]["perlmutter"]["backend"] == "ssh"


class TestGetClient:
    def test_unknown_target(self, tmp_path: Path):
        from asp.remote.client import get_client

        config = {"target": "unknown", "clusters": {}}
        import yaml

        (tmp_path / "asp-remote.yaml").write_text(yaml.safe_dump(config))
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

        (tmp_path / "asp-remote.yaml").write_text(yaml.safe_dump(config))
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

        (tmp_path / "asp-remote.yaml").write_text(yaml.safe_dump(config))
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

        (tmp_path / "asp-remote.yaml").write_text(yaml.safe_dump(config))
        client = get_client(tmp_path)
        assert isinstance(client, SSHBackend)

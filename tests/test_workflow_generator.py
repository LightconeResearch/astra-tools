"""Tests for workflow generator logic."""

import yaml

from asp.workflow.generator import generate_cwl_skeleton


class TestGenerateCWLSkeleton:
    """Tests for generate_cwl_skeleton function."""

    def test_generates_workflow_not_commandlinetool(self):
        """Generated CWL should be class: Workflow, not CommandLineTool."""
        analysis = {
            "version": "1.0",
            "analysis": {
                "name": "Test Analysis",
                "problem": "Test problem",
                "inputs": [{"id": "data", "type": "data"}],
                "outputs": [{"id": "result", "type": "metric", "dtype": "float"}],
            },
            "decisions": {
                "model": {
                    "label": "Model",
                    "type": "method",
                    "default": "rf",
                    "options": {"rf": {"label": "Random Forest"}},
                },
            },
        }
        cwl_str = generate_cwl_skeleton(analysis)
        cwl = yaml.safe_load(cwl_str)

        assert cwl["class"] == "Workflow"
        assert "baseCommand" not in cwl
        assert cwl["cwlVersion"] == "v1.2"

    def test_excludes_analysis_and_literature_inputs(self):
        """Only data-type inputs should be included in the workflow."""
        analysis = {
            "version": "1.0",
            "analysis": {
                "name": "Test Analysis",
                "problem": "Test problem",
                "inputs": [
                    {"id": "train_data", "type": "data", "description": "Training data"},
                    {"id": "prior_study", "type": "analysis", "description": "Prior analysis"},
                    {"id": "paper_ref", "type": "literature", "description": "Reference paper"},
                ],
                "outputs": [{"id": "result", "type": "metric", "dtype": "float"}],
            },
            "decisions": {
                "model": {
                    "label": "Model",
                    "type": "method",
                    "default": "rf",
                    "options": {"rf": {"label": "Random Forest"}},
                },
            },
        }
        cwl_str = generate_cwl_skeleton(analysis)
        cwl = yaml.safe_load(cwl_str)

        # Only data input should be present
        assert "train_data" in cwl["inputs"]
        assert "prior_study" not in cwl["inputs"]
        assert "paper_ref" not in cwl["inputs"]

    def test_data_inputs_are_file_type(self):
        """Data inputs should have CWL type: File."""
        analysis = {
            "version": "1.0",
            "analysis": {
                "name": "Test",
                "problem": "Test",
                "inputs": [{"id": "data", "type": "data", "description": "Input data"}],
                "outputs": [{"id": "result", "type": "metric", "dtype": "float"}],
            },
            "decisions": {},
        }
        cwl_str = generate_cwl_skeleton(analysis)
        cwl = yaml.safe_load(cwl_str)

        assert cwl["inputs"]["data"]["type"] == "File"

    def test_references_steps_main_cwl(self):
        """Workflow should have a step referencing steps/main.cwl."""
        analysis = {
            "version": "1.0",
            "analysis": {
                "name": "Test",
                "problem": "Test",
                "inputs": [{"id": "data", "type": "data"}],
                "outputs": [{"id": "result", "type": "metric", "dtype": "float"}],
            },
            "decisions": {
                "model": {
                    "label": "Model",
                    "type": "method",
                    "default": "rf",
                    "options": {"rf": {"label": "Random Forest"}},
                },
            },
        }
        cwl_str = generate_cwl_skeleton(analysis)
        cwl = yaml.safe_load(cwl_str)

        assert "steps" in cwl
        assert "run_analysis" in cwl["steps"]
        assert cwl["steps"]["run_analysis"]["run"] == "steps/main.cwl"

    def test_outputs_use_output_source(self):
        """Workflow outputs should use outputSource referencing step outputs."""
        analysis = {
            "version": "1.0",
            "analysis": {
                "name": "Test",
                "problem": "Test",
                "inputs": [{"id": "data", "type": "data"}],
                "outputs": [
                    {"id": "accuracy", "type": "metric", "dtype": "float", "primary": True},
                    {"id": "model_file", "type": "model"},
                ],
            },
            "decisions": {},
        }
        cwl_str = generate_cwl_skeleton(analysis)
        cwl = yaml.safe_load(cwl_str)

        assert cwl["outputs"]["accuracy"]["outputSource"] == "run_analysis/accuracy"
        assert cwl["outputs"]["model_file"]["outputSource"] == "run_analysis/model_file"

    def test_step_connects_inputs_to_workflow_inputs(self):
        """Step inputs should be connected to workflow inputs."""
        analysis = {
            "version": "1.0",
            "analysis": {
                "name": "Test",
                "problem": "Test",
                "inputs": [{"id": "iris_data", "type": "data"}],
                "outputs": [{"id": "result", "type": "metric", "dtype": "float"}],
            },
            "decisions": {
                "scaling": {
                    "label": "Scaling",
                    "type": "method",
                    "default": "standard",
                    "options": {"standard": {"label": "Standard"}},
                },
                "model": {
                    "label": "Model",
                    "type": "method",
                    "default": "rf",
                    "options": {"rf": {"label": "RF"}},
                },
            },
        }
        cwl_str = generate_cwl_skeleton(analysis)
        cwl = yaml.safe_load(cwl_str)

        step_in = cwl["steps"]["run_analysis"]["in"]
        # Data input should be connected
        assert step_in["iris_data"] == "iris_data"
        # Decision inputs should be connected
        assert step_in["scaling"] == "scaling"
        assert step_in["model"] == "model"

    def test_step_lists_all_outputs(self):
        """Step should list all workflow outputs in its 'out' field."""
        analysis = {
            "version": "1.0",
            "analysis": {
                "name": "Test",
                "problem": "Test",
                "inputs": [{"id": "data", "type": "data"}],
                "outputs": [
                    {"id": "accuracy", "type": "metric", "dtype": "float"},
                    {"id": "f1_score", "type": "metric", "dtype": "float"},
                    {"id": "trained_model", "type": "model"},
                ],
            },
            "decisions": {},
        }
        cwl_str = generate_cwl_skeleton(analysis)
        cwl = yaml.safe_load(cwl_str)

        step_out = cwl["steps"]["run_analysis"]["out"]
        assert "accuracy" in step_out
        assert "f1_score" in step_out
        assert "trained_model" in step_out

    def test_decisions_with_dict_values_flatten_correctly(self):
        """Dict values in decisions should produce multiple CWL inputs."""
        analysis = {
            "version": "1.0",
            "analysis": {
                "name": "Test",
                "problem": "Test",
                "inputs": [{"id": "data", "type": "data"}],
                "outputs": [{"id": "result", "type": "metric", "dtype": "float"}],
            },
            "decisions": {
                "scaling": {
                    "label": "Scaling",
                    "type": "method",
                    "default": "standard",
                    "options": {
                        "standard": {
                            "label": "Standard",
                            "value": {"method": "standard", "with_mean": True},
                        },
                    },
                },
            },
        }
        cwl_str = generate_cwl_skeleton(analysis)
        cwl = yaml.safe_load(cwl_str)

        # Dict value should be flattened to scaling_method and scaling_with_mean
        assert "scaling_method" in cwl["inputs"]
        assert "scaling_with_mean" in cwl["inputs"]

    def test_header_comment_includes_analysis_name(self):
        """Generated CWL should have a header comment with the analysis name."""
        analysis = {
            "version": "1.0",
            "analysis": {
                "name": "Iris Classification Study",
                "problem": "Test",
                "inputs": [{"id": "data", "type": "data"}],
                "outputs": [{"id": "result", "type": "metric", "dtype": "float"}],
            },
            "decisions": {},
        }
        cwl_str = generate_cwl_skeleton(analysis)

        assert "# Analysis: Iris Classification Study" in cwl_str

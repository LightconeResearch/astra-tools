"""Tests for `astra.resolve` — what a universe actually produces.

The canonical nested example (`examples/iris_pipeline`) is the fixture
that matters: it is the only place the whole set of cross-scope rules
appears together — an inherited decision, an input reaching sideways into
a sibling sub-analysis, and a root output re-exporting a grandchild's.
"""

from pathlib import Path

import pytest

from astra.helpers import iter_sub_analyses, load_yaml, parse_from_path
from astra.resolve import (
    iter_analysis_nodes,
    render_command,
    resolve_outputs,
    resolve_universe,
)

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture
def pipeline() -> dict:
    return load_yaml(EXAMPLES / "iris_pipeline" / "astra.yaml")


def universe(name: str) -> dict:
    return load_yaml(EXAMPLES / "iris_pipeline" / "universes" / f"{name}.yaml")


def by_id(outputs):
    return {o.id: o for o in outputs}


class TestParseFromPath:
    def test_upward_and_descent(self):
        assert parse_from_path("../id") == (1, ["id"])
        assert parse_from_path("../../id") == (2, ["id"])
        assert parse_from_path("../scope.id") == (1, ["scope", "id"])
        assert parse_from_path("scope.sub.id") == (0, ["scope", "sub", "id"])

    def test_malformed(self):
        assert parse_from_path("") is None
        assert parse_from_path("../") is None
        assert parse_from_path("a..b") is None
        assert parse_from_path("Bad.Id") is None


class TestIterAnalysisNodes:
    def test_root_comes_first_with_an_empty_scope(self, pipeline: dict):
        scopes = [scope for scope, _ in iter_analysis_nodes(pipeline)]
        assert scopes[0] == ()
        assert ("feature_extraction",) in scopes
        assert ("classification",) in scopes

    def test_the_scope_is_what_names_a_nested_id(self, pipeline: dict):
        nodes = dict(iter_analysis_nodes(pipeline))
        node = nodes[("classification",)]
        assert {o["id"] for o in node["outputs"]} == {"predictions", "accuracy"}

    def test_iter_sub_analyses_is_the_same_walk_without_the_scope(self, pipeline: dict):
        """Two views of one walker, so what counts as a sub-analysis cannot
        drift between the tooling that needs the scope and the tooling that
        does not."""
        scoped = [node for scope, node in iter_analysis_nodes(pipeline) if scope]
        assert list(iter_sub_analyses(pipeline)) == scoped

    def test_a_resolved_externals_children_are_reached_too(self):
        """An external sub-analysis is descended into like any other: before
        `resolve_analysis_tree` it has nothing to descend into, and after it
        that content is the sub-analysis."""
        data = {"analyses": {"stage": {"path": "stage", "analyses": {"inner": {"id": "inner"}}}}}
        assert [scope for scope, _ in iter_analysis_nodes(data)] == [
            (),
            ("stage",),
            ("stage", "inner"),
        ]


class TestResolveUniverse:
    def test_a_sub_analysis_decision_is_qualified(self, pipeline: dict):
        settled = resolve_universe(pipeline, universe("baseline"))
        assert settled["feature_extraction.method"] == "pca"
        assert settled["classification.classifier"] == "logistic"

    def test_an_inherited_decision_takes_the_ancestors_option(self, pipeline: dict):
        """`seed: from: ../random_seed` — the sub-analysis names it `seed`
        and never states a value, so nothing but resolution supplies one."""
        settled = resolve_universe(pipeline, universe("baseline"))
        assert settled["random_seed"] == "seed_42"
        assert settled["feature_extraction.seed"] == "seed_42"
        assert settled["classification.split"] == settled["test_split"]

    def test_a_conditional_decision_declared_before_its_condition_is_kept(self):
        """`when:` reads the whole universe, not the decisions that happen
        to be declared above it — which is what the validator compares
        against, so the two must agree on what a universe settles."""
        spec = {
            "decisions": {
                "trees": {"when": "model.forest", "options": {"fifty": {}, "hundred": {}}},
                "model": {"options": {"forest": {}, "logistic": {}}},
            }
        }
        chosen = {"decisions": {"model": "forest", "trees": "fifty"}}
        assert resolve_universe(spec, chosen) == {"model": "forest", "trees": "fifty"}

    def test_an_unmet_condition_still_drops_the_decision(self):
        spec = {
            "decisions": {
                "trees": {"when": "model.forest", "options": {"fifty": {}}},
                "model": {"options": {"forest": {}, "logistic": {}}},
            }
        }
        chosen = {"decisions": {"model": "logistic", "trees": "fifty"}}
        assert resolve_universe(spec, chosen) == {"model": "logistic"}

    def test_universes_differ_where_the_universe_file_differs(self, pipeline: dict):
        baseline = resolve_universe(pipeline, universe("baseline"))
        mlp = resolve_universe(pipeline, universe("mlp_svm"))
        assert baseline["feature_extraction.method"] == "pca"
        assert mlp["feature_extraction.method"] == "mlp_encoder"
        assert baseline["random_seed"] == mlp["random_seed"]

    def test_a_conditional_decision_is_left_out_where_it_is_inactive(self):
        data = {
            "decisions": {
                "model": {"options": {"linear": {}, "forest": {}}},
                "trees": {"when": "model.forest", "options": {"ten": {}, "fifty": {}}},
            }
        }
        active = resolve_universe(data, {"decisions": {"model": "forest", "trees": "fifty"}})
        assert active == {"model": "forest", "trees": "fifty"}
        inactive = resolve_universe(data, {"decisions": {"model": "linear", "trees": "fifty"}})
        assert inactive == {"model": "linear"}


class TestResolveOutputs:
    def test_every_output_in_the_tree_is_returned_qualified(self, pipeline: dict):
        found = by_id(resolve_outputs(pipeline, universe("baseline")))
        assert "feature_extraction.features" in found
        assert "classification.accuracy" in found
        assert "pipeline_summary" in found

    def test_a_recipe_is_what_marks_an_output_executable(self, pipeline: dict):
        found = by_id(resolve_outputs(pipeline, universe("baseline")))
        assert found["classification.accuracy"].command
        assert found["accuracy"].command is None  # a re-export computes nothing

    def test_a_re_export_names_what_actually_produces_it(self, pipeline: dict):
        found = by_id(resolve_outputs(pipeline, universe("baseline")))
        assert found["accuracy"].reexports == "classification.accuracy"
        assert found["feature_plot"].reexports == "feature_extraction.feature_plot"

    def test_an_input_reaching_into_a_sibling_resolves_to_that_output(self, pipeline: dict):
        """`classification.features` is `from: ../feature_extraction.features`
        — the seam between the two stages, and the whole point of the
        example."""
        found = by_id(resolve_outputs(pipeline, universe("baseline")))
        (features,) = found["classification.predictions"].inputs
        assert features.id == "features"
        assert features.produced_by == "feature_extraction.features"
        assert features.source is None

    def test_an_input_aliasing_an_ancestors_input_inherits_its_source(self, pipeline: dict):
        """`raw_features` is `from: ../iris_data`, which carries the source."""
        found = by_id(resolve_outputs(pipeline, universe("baseline")))
        (raw,) = found["feature_extraction.features"].inputs
        assert raw.source == "sklearn.datasets.load_iris"
        assert raw.produced_by is None

    def test_an_input_naming_a_sibling_output_resolves_within_the_scope(self, pipeline: dict):
        found = by_id(resolve_outputs(pipeline, universe("baseline")))
        (predictions,) = found["classification.accuracy"].inputs
        assert predictions.produced_by == "classification.predictions"

    def test_an_input_naming_a_sub_analysis_output_resolves_to_it(self):
        """`inputs: [stage.features]` is the qualified form the validator
        accepts alongside a plain sibling id — a consumer building a DAG
        loses the edge if it does not resolve."""
        spec = {
            "outputs": [{"id": "report", "inputs": ["stage.features"], "recipe": {"command": "x"}}],
            "analyses": {"stage": {"outputs": [{"id": "features", "recipe": {"command": "y"}}]}},
        }
        found = by_id(resolve_outputs(spec, {}))
        (features,) = found["report"].inputs
        assert features.id == "stage.features"
        assert features.produced_by == "stage.features"
        assert features.source is None

    def test_a_qualified_input_follows_the_re_export_beneath_it(self):
        spec = {
            "outputs": [{"id": "report", "inputs": ["stage.features"], "recipe": {"command": "x"}}],
            "analyses": {
                "stage": {
                    "outputs": [{"id": "features", "from": "inner.features"}],
                    "analyses": {
                        "inner": {"outputs": [{"id": "features", "recipe": {"command": "y"}}]}
                    },
                }
            },
        }
        (features,) = by_id(resolve_outputs(spec, {}))["report"].inputs
        assert features.produced_by == "stage.inner.features"

    def test_an_ancestor_alias_reads_that_scopes_inputs_not_its_outputs(self):
        """`from: ../data` names an ancestor *input*, which is what
        `_validate_input_from` checks it against — a same-named output
        there must not stand in for it and lose the source."""
        spec = {
            "inputs": [{"id": "data", "source": "s3://raw"}],
            "outputs": [{"id": "data", "recipe": {"command": "x"}}],
            "analyses": {
                "stage": {
                    "inputs": [{"id": "d", "from": "../data"}],
                    "outputs": [{"id": "fit", "inputs": ["d"], "recipe": {"command": "y"}}],
                }
            },
        }
        (d,) = by_id(resolve_outputs(spec, {}))["stage.fit"].inputs
        assert d.source == "s3://raw"
        assert d.produced_by is None

    def test_decisions_are_keyed_by_the_id_the_recipe_writes(self, pipeline: dict):
        """A recipe inside a sub-analysis writes `{decisions.method}`, not
        the qualified id — so that is the key it gets."""
        found = by_id(resolve_outputs(pipeline, universe("mlp_svm")))
        assert found["feature_extraction.features"].decisions == {
            "method": "mlp_encoder",
            "n_components": "two",
            "seed": "seed_42",
        }

    def test_the_flat_example_resolves_too(self):
        root = EXAMPLES / "iris"
        data = load_yaml(root / "astra.yaml")
        found = by_id(resolve_outputs(data, load_yaml(root / "universes" / "baseline.yaml")))
        assert found["trained_output"].command
        assert all(o.scope == () for o in found.values())


class TestConditionalOutputs:
    """`when:` on an output, which decides whether it exists at all here."""

    SPEC = {
        "decisions": {"method": {"options": {"bayesian": {}, "frequentist": {}}}},
        "outputs": [
            {"id": "always", "recipe": {"command": "echo a"}},
            {"id": "only_bayes", "when": "method.bayesian", "recipe": {"command": "echo b"}},
            {"id": "not_bayes", "when": "~method.bayesian", "recipe": {"command": "echo c"}},
        ],
    }

    def test_an_inactive_output_is_not_produced(self):
        found = by_id(resolve_outputs(self.SPEC, {"decisions": {"method": "frequentist"}}))
        assert set(found) == {"always", "not_bayes"}

    def test_the_same_spec_produces_the_other_one_elsewhere(self):
        found = by_id(resolve_outputs(self.SPEC, {"decisions": {"method": "bayesian"}}))
        assert set(found) == {"always", "only_bayes"}

    def test_conditions_are_anded(self):
        spec = {
            "decisions": {
                "a": {"options": {"yes": {}, "no": {}}},
                "b": {"options": {"yes": {}, "no": {}}},
            },
            "outputs": [{"id": "both", "when": ["a.yes", "b.yes"], "recipe": {"command": "x"}}],
        }
        assert by_id(resolve_outputs(spec, {"decisions": {"a": "yes", "b": "yes"}}))
        assert not by_id(resolve_outputs(spec, {"decisions": {"a": "yes", "b": "no"}}))

    def test_a_condition_is_read_in_the_scope_that_wrote_it(self):
        """A sub-analysis's `when: method.pca` names its own decision, not
        a qualified one — the scope is where the condition is written."""
        spec = {
            "analyses": {
                "fe": {
                    "decisions": {"method": {"options": {"pca": {}, "mlp": {}}}},
                    "outputs": [
                        {"id": "loadings", "when": "method.pca", "recipe": {"command": "x"}}
                    ],
                }
            }
        }
        chosen = {"analyses": {"fe": {"decisions": {"method": "pca"}}}}
        assert "fe.loadings" in by_id(resolve_outputs(spec, chosen))
        other = {"analyses": {"fe": {"decisions": {"method": "mlp"}}}}
        assert "fe.loadings" not in by_id(resolve_outputs(spec, other))


class TestConditionalReExports:
    """A re-export carries no `when:` of its own, so it is exactly as
    conditional as the output it stands for. Returning one whose target was
    conditioned away hands a runner a target it cannot build."""

    SPEC = {
        "outputs": [{"id": "plot", "from": "stage.plot"}],
        "analyses": {
            "stage": {
                "decisions": {"m": {"options": {"a": {}, "b": {}}}},
                "outputs": [{"id": "plot", "when": "m.a", "recipe": {"command": "x"}}],
            }
        },
    }

    def test_the_re_export_goes_when_its_target_goes(self):
        chosen = {"analyses": {"stage": {"decisions": {"m": "b"}}}}
        assert by_id(resolve_outputs(self.SPEC, chosen)) == {}

    def test_and_stays_when_its_target_stays(self):
        chosen = {"analyses": {"stage": {"decisions": {"m": "a"}}}}
        found = by_id(resolve_outputs(self.SPEC, chosen))
        assert set(found) == {"plot", "stage.plot"}
        assert found["plot"].reexports == "stage.plot"

    def test_dropping_cascades_through_a_chain_of_re_exports(self):
        spec = {
            "outputs": [{"id": "plot", "from": "stage.plot"}],
            "analyses": {
                "stage": {
                    "outputs": [{"id": "plot", "from": "inner.plot"}],
                    "analyses": {
                        "inner": {
                            "decisions": {"m": {"options": {"a": {}, "b": {}}}},
                            "outputs": [{"id": "plot", "when": "m.a", "recipe": {"command": "x"}}],
                        }
                    },
                }
            },
        }
        chosen = {"analyses": {"stage": {"analyses": {"inner": {"decisions": {"m": "b"}}}}}}
        assert by_id(resolve_outputs(spec, chosen)) == {}


class TestRenderCommand:
    def test_every_placeholder_form(self):
        rendered = render_command(
            "run {inputs.data} --seed {decisions.seed} --all {inputs} --out {output}",
            inputs={"data": "data/x.csv", "extra": "data/y.csv"},
            decisions={"seed": "seed_42"},
            output="results/baseline/fit",
        )
        assert rendered == (
            "run data/x.csv --seed seed_42 --all data/x.csv data/y.csv --out results/baseline/fit"
        )

    def test_literal_braces_survive(self):
        assert render_command("echo {{x}}", inputs={}, decisions={}, output="o") == "echo {x}"

    @pytest.mark.parametrize(
        "command",
        [
            "run {nonsense}",
            "run {inputs.missing}",
            "run {decisions.missing}",
            "run {output:>10}",
        ],
    )
    def test_a_placeholder_that_cannot_be_filled_is_an_error(self, command: str):
        """Substituting nothing silently would produce a command that runs
        and means something else."""
        with pytest.raises(ValueError):
            render_command(command, inputs={"data": "d"}, decisions={"seed": "s"}, output="o")


class TestSelectedUniverse:
    """A sub-analysis node may name one of its *own* universes instead of
    listing decisions inline. Loading that file is what `semantic.py` says
    is "done by the caller/resolver"."""

    def _project(self, tmp_path: Path) -> tuple[dict, Path]:
        sub = tmp_path / "stage"
        (sub / "universes").mkdir(parents=True)
        (sub / "astra.yaml").write_text(
            "id: stage\nversion: '1.0'\nname: Stage\n"
            "decisions:\n  method:\n    options:\n      pca: {}\n      mlp: {}\n"
            "outputs:\n  - id: features\n    type: data\n    decisions: [method]\n"
            "    recipe:\n      command: run --method {decisions.method}\n"
        )
        (sub / "universes" / "fast.yaml").write_text("id: fast\ndecisions:\n  method: pca\n")
        (sub / "universes" / "deep.yaml").write_text("id: deep\ndecisions:\n  method: mlp\n")
        data = {"analyses": {"stage": {"path": "stage", **load_yaml(sub / "astra.yaml")}}}
        return data, tmp_path

    def test_the_named_universe_supplies_the_decisions(self, tmp_path: Path):
        data, base = self._project(tmp_path)
        chosen = {"analyses": {"stage": {"universe": "deep"}}}
        assert resolve_universe(data, chosen, base) == {"stage.method": "mlp"}

    def test_a_different_name_selects_differently(self, tmp_path: Path):
        data, base = self._project(tmp_path)
        chosen = {"analyses": {"stage": {"universe": "fast"}}}
        assert resolve_universe(data, chosen, base) == {"stage.method": "pca"}
        outputs = by_id(resolve_outputs(data, chosen, base))
        assert outputs["stage.features"].decisions == {"method": "pca"}

    def test_without_a_base_path_the_reference_is_skipped(self, tmp_path: Path):
        """There is nothing to resolve it against, and inventing a root
        would be worse than leaving the decision unsettled."""
        data, _ = self._project(tmp_path)
        assert resolve_universe(data, {"analyses": {"stage": {"universe": "deep"}}}) == {}

    def test_an_empty_universe_file_leaves_the_node_as_it_stands(self, tmp_path: Path):
        """A file that parses to `None` is the validator's to report; this
        module promises not to raise on anything unresolvable."""
        data, base = self._project(tmp_path)
        (base / "stage" / "universes" / "blank.yaml").write_text("# nothing here\n")
        chosen = {"analyses": {"stage": {"universe": "blank"}}}
        assert resolve_universe(data, chosen, base) == {}

    def test_inline_decisions_still_work_beside_it(self, tmp_path: Path):
        data, base = self._project(tmp_path)
        chosen = {"analyses": {"stage": {"decisions": {"method": "pca"}}}}
        assert resolve_universe(data, chosen, base) == {"stage.method": "pca"}

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
    PlannedOutput,
    References,
    iter_analysis_nodes,
    plan,
    render_command,
    resolve_outputs,
    resolve_universe,
    split_pin,
)
from astra.universes import effective_universe

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture
def pipeline() -> dict:
    return load_yaml(EXAMPLES / "iris_pipeline" / "astra.yaml")


def universe(name: str) -> dict:
    """The effective selection of one of ``iris_pipeline``'s universes."""
    effective = effective_universe(load_yaml(EXAMPLES / "iris_pipeline" / "astra.yaml"), name)
    assert effective is not None
    return effective.selection


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

    def test_format_is_the_declared_serialization(self, pipeline: dict):
        found = by_id(resolve_outputs(pipeline, universe("baseline")))
        assert found["classification.accuracy"].format == "json"
        assert found["feature_extraction.feature_plot"].format == "png"

    def test_a_re_export_inherits_the_format_it_stands_for(self, pipeline: dict):
        """The schema forbids `format` on an alias, so resolving has to
        supply the terminal output's — otherwise a consumer holding a
        re-export cannot tell what it is about to open."""
        found = by_id(resolve_outputs(pipeline, universe("baseline")))
        assert found["accuracy"].definition.get("format") is None  # never declared
        assert found["accuracy"].format == "json"
        assert found["feature_plot"].format == "png"

    def test_format_is_none_where_the_spec_omits_it(self):
        """`format` is recommended, not required, so resolving must cope."""
        data = {
            "version": "1.0",
            "name": "No format",
            "outputs": [{"id": "result", "type": "metric"}],
        }
        found = by_id(resolve_outputs(data, {"id": "u", "decisions": {}}))
        assert found["result"].format is None

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
        data = load_yaml(EXAMPLES / "iris" / "astra.yaml")
        baseline = effective_universe(data, "baseline")
        assert baseline is not None
        found = by_id(resolve_outputs(data, baseline.selection))
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


class TestMalformedConditions:
    """A `when:` that does not parse resolves to nothing, rather than
    raising. Diagnosis belongs to the validator, which reports it as
    `INVALID_WHEN_REF` — and cannot, if parsing raises first."""

    @pytest.mark.parametrize("when", ["method", "method.pca.extra", "~method"])
    def test_an_unparseable_output_condition_leaves_the_output_out(self, when: str):
        spec = {"outputs": [{"id": "out", "when": when, "recipe": {"command": "x"}}]}
        assert by_id(resolve_outputs(spec, {})) == {}

    def test_an_unparseable_decision_condition_leaves_the_decision_unsettled(self):
        spec = {
            "decisions": {
                "method": {"options": {"pca": {}, "mlp": {}}},
                "trees": {"when": "method", "options": {"fifty": {}}},
            }
        }
        chosen = {"decisions": {"method": "pca", "trees": "fifty"}}
        assert resolve_universe(spec, chosen) == {"method": "pca"}


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
    """A universe's entry for a sub-analysis may name one of the universes
    that sub-analysis declares instead of listing decisions."""

    SPEC = {
        "analyses": {
            "stage": {
                "decisions": {
                    "method": {"options": {"pca": {}, "mlp": {}}},
                    "depth": {"options": {"shallow": {}, "deep": {}}},
                },
                "outputs": [
                    {
                        "id": "features",
                        "type": "data",
                        "decisions": ["method"],
                        "recipe": {"command": "run --method {decisions.method}"},
                    }
                ],
                "universes": [
                    {"id": "fast", "decisions": {"method": "pca", "depth": "shallow"}},
                    {"id": "slow", "derived_from": "fast", "decisions": {"method": "mlp"}},
                ],
            }
        }
    }

    def test_the_named_universe_supplies_the_decisions(self):
        chosen = {"analyses": {"stage": {"universe": "fast"}}}
        assert resolve_universe(self.SPEC, chosen) == {
            "stage.method": "pca",
            "stage.depth": "shallow",
        }

    def test_a_different_name_selects_differently(self):
        chosen = {"analyses": {"stage": {"universe": "slow"}}}
        outputs = by_id(resolve_outputs(self.SPEC, chosen))
        assert outputs["stage.features"].decisions == {"method": "mlp"}

    def test_a_named_diff_resolves_through_its_chain(self):
        chosen = {"analyses": {"stage": {"universe": "slow"}}}
        assert resolve_universe(self.SPEC, chosen) == {
            "stage.method": "mlp",
            "stage.depth": "shallow",
        }

    def test_an_unknown_name_leaves_the_sub_analysis_unsettled(self):
        """``UNKNOWN_SUB_UNIVERSE`` is the validator's to report - this module
        doesn't raise on anything it can't resolve."""
        chosen = {"analyses": {"stage": {"universe": "nope"}}}
        assert resolve_universe(self.SPEC, chosen) == {}

    def test_inline_decisions_still_work_beside_it(self):
        chosen = {"analyses": {"stage": {"decisions": {"method": "pca", "depth": "deep"}}}}
        assert resolve_universe(self.SPEC, chosen) == {
            "stage.method": "pca",
            "stage.depth": "deep",
        }


class TestReferences:
    """What references point at, and which outputs are built per universe."""

    SPEC = {
        "inputs": [{"id": "raw", "type": "data", "source": "raw.csv"}],
        "decisions": {"model": {"options": {"rf": {}, "svm": {}}}},
        "outputs": [
            {"id": "score", "inputs": ["raw"], "decisions": ["model"]},
            {"id": "report", "inputs": ["score"]},
            {"id": "comparison", "inputs": ["score#rf", "score#svm"]},
            {"id": "summary", "inputs": ["raw"]},
            {"id": "note", "inputs": ["raw"], "when": ["model.svm"]},
            {"id": "relayed", "from": "stage.fit"},
        ],
        "analyses": {
            "maker": {
                "decisions": {"k": {"options": {"a": {}, "b": {}}}},
                "outputs": [{"id": "made", "decisions": ["k"]}],
            },
            "stage": {
                "inputs": [{"id": "x", "from": "../raw"}, {"id": "s", "from": "../maker.made"}],
                "outputs": [{"id": "fit", "inputs": ["s"]}, {"id": "plain", "inputs": ["x"]}],
            },
        },
    }

    def test_split_pin(self):
        assert split_pin("score#rf") == ("score", "rf")
        assert split_pin("stage.fit") == ("stage.fit", None)

    def test_what_makes_an_output_per_universe(self):
        refs = References(self.SPEC)
        assert refs.per_universe("score")
        assert refs.per_universe("report")
        assert refs.per_universe("note")

    def test_pins_and_external_inputs_never_do(self):
        refs = References(self.SPEC)
        assert not refs.per_universe("comparison")
        assert not refs.per_universe("summary")

    def test_aliases_and_re_exports_are_what_they_point_at(self):
        """``stage.fit`` reads its sibling's ``maker.made`` through an input
        alias and ``relayed`` re-exports it. ``stage.plain`` reads the root's
        external input."""
        refs = References(self.SPEC)
        assert refs.per_universe("stage.fit")
        assert refs.per_universe("relayed")
        assert not refs.per_universe("stage.plain")

    def test_resolving_an_entry_sets_the_pin_aside(self):
        refs = References(self.SPEC)
        assert refs.resolve((), "score#rf").produced_by == "score"
        assert refs.resolve((), "relayed").produced_by == "stage.fit"
        assert refs.is_external((), "raw")
        assert refs.is_external(("stage",), "x")
        assert not refs.is_external(("stage",), "s")

    def test_iris(self):
        refs = References(load_yaml(EXAMPLES / "iris" / "astra.yaml"))
        assert refs.per_universe("f1_score")
        assert refs.per_universe("conclusion")
        assert not refs.per_universe("model_comparison")


class TestResolvedPins:
    def test_a_pinned_input_keeps_its_pin_and_resolves(self):
        data = load_yaml(EXAMPLES / "iris" / "astra.yaml")
        baseline = effective_universe(data, "baseline")
        assert baseline is not None
        comparison = by_id(resolve_outputs(data, baseline.selection))["model_comparison"]
        assert [(i.id, i.produced_by, i.pin) for i in comparison.inputs] == [
            ("accuracy#baseline", "accuracy", "baseline"),
            ("accuracy#svm_focused", "accuracy", "svm_focused"),
        ]
        assert not comparison.per_universe


class TestPlan:
    """Every output to build, where it goes and what it reads."""

    @staticmethod
    def planned(example: str) -> dict[tuple[str | None, str], PlannedOutput]:
        entries = plan(load_yaml(EXAMPLES / example / "astra.yaml"))
        return {(p.universe, p.output.id): p for p in entries}

    def test_an_output_built_once_is_planned_once_and_reads_both_universes(self):
        found = self.planned("iris")
        comparison = found[(None, "model_comparison")]
        assert comparison.path == "results/model_comparison.csv"
        assert comparison.reads == {
            "accuracy#baseline": "results/baseline/accuracy.json",
            "accuracy#svm_focused": "results/svm_focused/accuracy.json",
        }
        assert [key for key in found if key[1] == "model_comparison"] == [
            (None, "model_comparison")
        ]

    def test_an_output_built_per_universe_is_planned_in_each(self):
        found = self.planned("iris")
        for universe in ("baseline", "svm_focused"):
            f1 = found[(universe, "f1_score")]
            assert f1.path == f"results/{universe}/f1_score.json"
            assert f1.reads == {"trained_output": f"results/{universe}/trained_output.pkl"}
        assert len(found) == 1 + 5 * 2

    def test_sub_analysis_results_use_qualified_ids(self):
        found = self.planned("iris_pipeline")
        predictions = found[("mlp_svm", "classification.predictions")]
        assert predictions.path == "results/mlp_svm/classification.predictions.csv"
        assert predictions.reads == {"features": "results/mlp_svm/feature_extraction.features.npy"}
        features = found[("baseline", "feature_extraction.features")]
        assert features.reads == {"raw_features": "sklearn.datasets.load_iris"}

    def test_re_exports_make_no_file_of_their_own(self):
        found = self.planned("iris_pipeline")
        assert not [key for key in found if key[1] in ("accuracy", "feature_plot")]

    def test_without_universes_only_outputs_built_once_are_planned(self):
        data = load_yaml(EXAMPLES / "iris" / "astra.yaml")
        data["universes"] = []
        assert [p.output.id for p in plan(data)] == ["model_comparison"]

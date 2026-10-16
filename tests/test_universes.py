"""Tests for `astra.universes` - what a universe selects once its
``derived_from`` chain is followed."""

from astra.universes import declared_universes, derived_from_chain, effective_universe

DECISIONS = {
    "mode": {"options": {"basic": {}, "advanced": {}}},
    "backend": {"options": {"cpu": {}, "gpu": {}}},
    "gpu_optimization": {
        "when": ["mode.advanced", "backend.gpu"],
        "options": {"tensor_cores": {}, "standard": {}},
    },
}


def analysis(*universes: dict) -> dict:
    return {"decisions": DECISIONS, "universes": list(universes)}


GPU = {
    "id": "gpu",
    "decisions": {"mode": "advanced", "backend": "gpu", "gpu_optimization": "tensor_cores"},
}


class TestChains:
    def test_the_first_declaration_of_an_id_wins(self):
        node = analysis({"id": "a", "decisions": {"mode": "basic"}}, {"id": "a"})
        assert declared_universes(node)["a"]["decisions"] == {"mode": "basic"}

    def test_a_chain_lists_the_universe_then_its_bases(self):
        universes = {"a": {}, "b": {"derived_from": "a"}, "c": {"derived_from": "b"}}
        assert derived_from_chain(universes, "c") == ["c", "b", "a"]

    def test_an_unknown_link_or_a_loop_gives_none(self):
        assert derived_from_chain({"b": {"derived_from": "nope"}}, "b") is None
        loop = {"a": {"derived_from": "b"}, "b": {"derived_from": "a"}}
        assert derived_from_chain(loop, "a") is None
        assert effective_universe(analysis(), "nope") is None


class TestEffectiveSelection:
    def test_a_diff_writes_its_decisions_over_its_base(self):
        node = analysis(
            GPU, {"id": "std", "derived_from": "gpu", "decisions": {"gpu_optimization": "standard"}}
        )
        effective = effective_universe(node, "std")
        assert effective is not None
        assert effective.selection["decisions"] == {
            "mode": "advanced",
            "backend": "gpu",
            "gpu_optimization": "standard",
        }
        assert effective.inherited == {"mode", "backend"}

    def test_sub_analysis_entries_are_inherited_per_sub_analysis(self):
        node = analysis(
            {
                "id": "a",
                "analyses": {
                    "x": {"decisions": {"p": "1", "q": "1"}},
                    "y": {"decisions": {"r": "1"}},
                },
            },
            {"id": "b", "derived_from": "a", "analyses": {"x": {"decisions": {"q": "2"}}}},
        )
        effective = effective_universe(node, "b")
        assert effective is not None
        assert effective.selection["analyses"] == {
            "x": {"decisions": {"p": "1", "q": "2"}},
            "y": {"decisions": {"r": "1"}},
        }
        assert effective.inherited == {"x.p", "y.r"}

    def test_an_entry_naming_a_universe_replaces_the_inherited_entry(self):
        node = analysis(
            {"id": "a", "analyses": {"x": {"decisions": {"p": "1"}}}},
            {"id": "b", "derived_from": "a", "analyses": {"x": {"universe": "fast"}}},
            {"id": "c", "derived_from": "b", "analyses": {"x": {"decisions": {"p": "2"}}}},
        )
        b = effective_universe(node, "b")
        c = effective_universe(node, "c")
        assert b is not None and c is not None
        assert b.selection["analyses"]["x"] == {"universe": "fast"}
        assert c.selection["analyses"]["x"] == {"decisions": {"p": "2"}}

    def test_an_inherited_selection_that_is_switched_off_is_dropped(self):
        node = analysis(GPU, {"id": "cpu", "derived_from": "gpu", "decisions": {"backend": "cpu"}})
        effective = effective_universe(node, "cpu")
        assert effective is not None
        assert effective.selection["decisions"] == {"mode": "advanced", "backend": "cpu"}

    def test_a_condition_on_the_parent_is_left_for_later(self):
        """On its own a sub-analysis can't tell what ``m`` (its parent's
        ``mode``) is, so the inherited ``depth`` is kept."""
        stage = {
            "decisions": {
                "m": {"from": "../mode"},
                "depth": {"when": ["m.full"], "options": {"a": {}, "b": {}}},
                "tol": {"options": {"lo": {}, "hi": {}}},
            },
            "universes": [
                {"id": "deep", "decisions": {"depth": "a", "tol": "lo"}},
                {"id": "lax", "derived_from": "deep", "decisions": {"tol": "hi"}},
            ],
        }
        effective = effective_universe(stage, "lax")
        assert effective is not None
        assert effective.selection["decisions"] == {"depth": "a", "tol": "hi"}

    def test_a_condition_on_the_parent_is_judged_in_context(self):
        """In a root universe ``m`` has its parent's value - switching
        ``mode`` to ``fast`` drops the ``depth`` the diff inherited."""
        root = {
            "decisions": {"mode": {"options": {"fast": {}, "full": {}}}},
            "analyses": {
                "stage": {
                    "decisions": {
                        "m": {"from": "../mode"},
                        "depth": {"when": ["m.full"], "options": {"a": {}, "b": {}}},
                    }
                }
            },
            "universes": [
                {
                    "id": "full",
                    "decisions": {"mode": "full"},
                    "analyses": {"stage": {"decisions": {"depth": "a"}}},
                },
                {"id": "fast", "derived_from": "full", "decisions": {"mode": "fast"}},
            ],
        }
        effective = effective_universe(root, "fast")
        assert effective is not None
        assert effective.selection["analyses"]["stage"]["decisions"] == {}

    def test_a_selection_the_universe_makes_itself_is_kept(self):
        """So that the validator can report it as inactive."""
        node = analysis(
            GPU,
            {
                "id": "cpu",
                "derived_from": "gpu",
                "decisions": {"backend": "cpu", "gpu_optimization": "standard"},
            },
        )
        effective = effective_universe(node, "cpu")
        assert effective is not None
        assert effective.selection["decisions"]["gpu_optimization"] == "standard"

"""Tests for RO-Crate export from YAML."""

from __future__ import annotations

import json
from pathlib import Path

from astra.export import export_rocrate
from astra.loader import load_yaml

EXAMPLES = Path(__file__).parent.parent / "examples"


class TestExportIris:
    def test_produces_rocrate(self, tmp_path: Path) -> None:
        data = load_yaml(EXAMPLES / "iris")
        export_rocrate(data, tmp_path / "crate")
        assert (tmp_path / "crate" / "ro-crate-metadata.json").exists()

    def test_valid_jsonld(self, tmp_path: Path) -> None:
        data = load_yaml(EXAMPLES / "iris")
        export_rocrate(data, tmp_path / "crate")
        meta = json.loads((tmp_path / "crate" / "ro-crate-metadata.json").read_text())
        assert "@context" in meta
        assert "@graph" in meta
        assert meta["@context"][0] == "https://w3id.org/ro/crate/1.2/context"

    def test_entity_count(self, tmp_path: Path) -> None:
        data = load_yaml(EXAMPLES / "iris")
        export_rocrate(data, tmp_path / "crate")
        meta = json.loads((tmp_path / "crate" / "ro-crate-metadata.json").read_text())
        # Root + metadata + profile + author + 2 inputs + 6 outputs + 6 recipes
        # + 4 decisions + 10 options + 2 universes + 8 selections = 42
        assert len(meta["@graph"]) >= 40

    def test_decisions_present(self, tmp_path: Path) -> None:
        data = load_yaml(EXAMPLES / "iris")
        export_rocrate(data, tmp_path / "crate")
        meta = json.loads((tmp_path / "crate" / "ro-crate-metadata.json").read_text())
        decisions = [
            e
            for e in meta["@graph"]
            if isinstance(e.get("@type"), list) and "ASTRADecision" in e["@type"]
        ]
        assert len(decisions) == 4
        names = {d["name"] for d in decisions}
        assert names == {"scaling", "model", "test_size", "random_seed"}

    def test_constraints_present(self, tmp_path: Path) -> None:
        data = load_yaml(EXAMPLES / "iris")
        export_rocrate(data, tmp_path / "crate")
        meta = json.loads((tmp_path / "crate" / "ro-crate-metadata.json").read_text())
        # minmax should have incompatibleWith
        minmax = next(
            e for e in meta["@graph"] if e.get("@id") == "#decision/scaling/option/minmax"
        )
        assert "incompatibleWith" in minmax

    def test_universes_present(self, tmp_path: Path) -> None:
        data = load_yaml(EXAMPLES / "iris")
        export_rocrate(data, tmp_path / "crate")
        meta = json.loads((tmp_path / "crate" / "ro-crate-metadata.json").read_text())
        universes = [e for e in meta["@graph"] if e.get("@type") == "ASTRAUniverse"]
        assert len(universes) == 2
        names = {u["name"] for u in universes}
        assert names == {"baseline", "svm_focused"}


class TestExportPipeline:
    def test_subcrates_created(self, tmp_path: Path) -> None:
        data = load_yaml(EXAMPLES / "iris_pipeline")
        export_rocrate(data, tmp_path / "crate")
        assert (tmp_path / "crate" / "feature_extraction" / "ro-crate-metadata.json").exists()
        assert (tmp_path / "crate" / "classification" / "ro-crate-metadata.json").exists()

    def test_cross_crate_selections(self, tmp_path: Path) -> None:
        data = load_yaml(EXAMPLES / "iris_pipeline")
        export_rocrate(data, tmp_path / "crate")
        meta = json.loads((tmp_path / "crate" / "ro-crate-metadata.json").read_text())
        sels = [e for e in meta["@graph"] if e.get("@type") == "ASTRAUniverseSelection"]
        dec_ids = {e["selectsDecision"]["@id"] for e in sels}
        assert "feature_extraction/#decision/method" in dec_ids
        assert "classification/#decision/classifier" in dec_ids

    def test_delegated_decision_in_subcrate(self, tmp_path: Path) -> None:
        data = load_yaml(EXAMPLES / "iris_pipeline")
        export_rocrate(data, tmp_path / "crate")
        fe_meta = json.loads(
            (tmp_path / "crate" / "feature_extraction" / "ro-crate-metadata.json").read_text()
        )
        seed = next(e for e in fe_meta["@graph"] if e.get("@id") == "#decision/seed")
        assert "delegatesTo" in seed

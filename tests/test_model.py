"""The model of `astra.yaml`: each class has its schema class's fields, and an analysis the
contract accepts is read whole."""

from __future__ import annotations

import dataclasses
import json

import pytest

from astra import model
from astra.contract import schema_file
from astra.load import load_yaml
from tests.conftest import DOCUMENTS

CLASSES = {
    model.Analysis: None,  # the schema's root
    model.AnalysisDeclaration: "AnalysisDeclaration__identifier_optional",
    model.Decision: "Decision__identifier_optional",
    model.Evidence: "Evidence",
    model.FragmentSelector: "FragmentSelector",
    model.Input: "Input__identifier_optional",
    model.Insight: "Insight__identifier_optional",
    model.Option: "Option__identifier_optional",
    model.Output: "Output__identifier_optional",
    model.Recipe: "Recipe",
    model.Resources: "Resources",
    model.TextQuoteSelector: "TextQuoteSelector",
    model.Universe: "Universe__identifier_optional",
}


def schema() -> dict[str, object]:
    loaded: dict[str, object] = json.loads(schema_file("analysis").read_text(encoding="utf-8"))
    return loaded


def test_every_class_of_the_schema_has_one() -> None:
    """Every class with fields; OutputType is an enumeration of strings."""
    defs = schema()["$defs"]
    assert isinstance(defs, dict)
    classes = {name for name, value in defs.items() if "properties" in value}
    assert classes == {name for name in CLASSES.values() if name is not None}


@pytest.mark.parametrize("cls", CLASSES, ids=lambda cls: cls.__name__)
def test_its_fields_are_its_schema_classs(cls: type) -> None:
    content = schema()
    name = CLASSES[cls]
    defined = content if name is None else content["$defs"][name]  # type: ignore[index]
    assert {f.name for f in dataclasses.fields(cls)} == set(defined["properties"])


def test_an_analysis_is_read_whole() -> None:
    """astra-spec's fixture of the core fields: inputs, outputs with references, decisions with
    constraints."""
    text = (DOCUMENTS / "valid" / "Analysis-002-core.yaml").read_bytes()
    analysis = model.Analysis.from_json(load_yaml(text).value)
    assert analysis.inputs["catalog"].path == "data/catalog.csv"
    estimates = analysis.outputs["estimates"]
    assert estimates.inputs == ("catalog", "calibration.spectra")
    assert estimates.recipe.command.startswith("python src/predict.py")
    options = analysis.decisions["method"].options
    assert options["neural_net"].requires == ("training.large",)
    assert analysis.decisions["training"].options["small"].excluded is not None
    assert analysis.universes == {} and analysis.analyses == {}


def test_an_import_selects_nothing() -> None:
    """§12 *Imports*: astra-spec's fixture of universes, whose `stage_alone` imports."""
    text = (DOCUMENTS / "valid" / "Analysis-004-universes.yaml").read_bytes()
    universes = model.Analysis.from_json(load_yaml(text).value).universes
    assert universes["stage_alone"].is_import
    assert universes["stage_alone"].decisions == {}
    assert not universes["svm_standard"].is_import
    assert universes["svm_standard"].derived_from == "rf_standard"

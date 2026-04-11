"""Core ASTRA RO-Crate wrapper.

Provides `ASTRACrate`, the primary API for creating, reading, and
manipulating ASTRA analyses stored as RO-Crates.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rocrate.model.contextentity import ContextEntity
from rocrate.rocrate import ROCrate

from astra.vocabulary import (
    ASTRA_CONTEXT,
    ASTRA_PROFILE_URL,
    INPUT_TYPES,
    OUTPUT_TYPES,
    PROP_ACTIVE_WHEN,
    PROP_ASTRA_VERSION,
    PROP_CONDITION,
    PROP_DEFAULT_OPTION,
    PROP_DELEGATES_TO,
    PROP_EXCLUDED_REASON,
    PROP_HAS_DECISION,
    PROP_HAS_EVIDENCE,
    PROP_HAS_FINDING,
    PROP_HAS_INPUT,
    PROP_HAS_OPTION,
    PROP_HAS_OUTPUT,
    PROP_HAS_PRIOR_INSIGHT,
    PROP_HAS_RESOURCES,
    PROP_HAS_SELECTION,
    PROP_HAS_SUCCESS_CRITERION,
    PROP_INCOMPATIBLE_WITH,
    PROP_INPUT_FROM,
    PROP_INPUT_TYPE,
    PROP_IS_DERIVED,
    PROP_IS_EXCLUDED,
    PROP_OUTPUT_FROM,
    PROP_OUTPUT_TYPE,
    PROP_REQUIRES_OPTION,
    PROP_SCOPE,
    PROP_SELECTS_DECISION,
    PROP_SELECTS_OPTION,
    PROP_SOURCE_COMMIT,
    PROP_SUPPORTS_INSIGHT,
    PROP_USE_OUTPUTS,
    ROCRATE_PROFILE,
    SCHEMA_ALTERNATE_NAME,
    SCHEMA_AUTHOR,
    SCHEMA_COMMENT,
    SCHEMA_CONFORMS_TO,
    SCHEMA_DATE_CREATED,
    SCHEMA_DESCRIPTION,
    SCHEMA_IDENTIFIER,
    SCHEMA_IS_BASED_ON,
    SCHEMA_KEYWORDS,
    SCHEMA_NAME,
    SCHEMA_OBJECT,
    SCHEMA_PRODUCER,
    SCHEMA_RESULT,
    SCHEMA_TEXT,
    SCHEMA_VERSION,
    TYPE_ANALYSIS,
    TYPE_DECISION,
    TYPE_EVIDENCE,
    TYPE_INPUT,
    TYPE_INSIGHT,
    TYPE_OPTION,
    TYPE_OUTPUT,
    TYPE_RECIPE,
    TYPE_RESOURCES,
    TYPE_SUCCESS_CRITERION,
    TYPE_UNIVERSE,
    TYPE_UNIVERSE_SELECTION,
    as_list,
    build_subcrate_prefix,
    criterion_id,
    decision_id,
    evidence_id,
    id_of,
    input_id,
    insight_id,
    option_id,
    output_id,
    parse_entity_name,
    recipe_id,
    ref,
    resources_id,
    selection_id,
    universe_id,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ref_list(ids: list[str]) -> list[dict[str, str]]:
    """Build a list of @id reference dicts."""
    return [ref(i) for i in ids]


def _entities_by_type(crate: ROCrate, type_name: str) -> list[ContextEntity]:
    """Get all entities in a crate matching a given @type."""
    results = []
    for entity in crate.get_entities():
        etype = entity.type
        if isinstance(etype, list):
            if type_name in etype:
                results.append(entity)
        elif etype == type_name:
            results.append(entity)
    return results


# ---------------------------------------------------------------------------
# ASTRACrate
# ---------------------------------------------------------------------------


class ASTRACrate:
    """High-level wrapper for ASTRA RO-Crate manipulation.

    Provides typed access to ASTRA entities within an RO-Crate,
    handling entity creation, cross-referencing, and serialization.
    """

    def __init__(
        self,
        name: str = "Untitled Analysis",
        *,
        description: str | None = None,
        version: str = "1.0",
        authors: list[str] | None = None,
        keywords: list[str] | None = None,
        container: str | None = None,
    ) -> None:
        """Create a new empty ASTRA crate."""
        self._crate = ROCrate()
        self._crate.metadata.PROFILE = ROCRATE_PROFILE
        self._crate.metadata[SCHEMA_CONFORMS_TO] = ref(ROCRATE_PROFILE)
        self._crate.metadata.extra_contexts = [ASTRA_CONTEXT]

        root = self._crate.root_dataset
        root._jsonld["@type"] = ["Dataset", TYPE_ANALYSIS]
        root[SCHEMA_CONFORMS_TO] = ref(ASTRA_PROFILE_URL)
        root[SCHEMA_NAME] = name
        root[PROP_ASTRA_VERSION] = version
        if description:
            root[SCHEMA_DESCRIPTION] = description
        if keywords:
            root[SCHEMA_KEYWORDS] = ", ".join(keywords)
        if container:
            root["containerImage"] = container

        if authors:
            author_refs = []
            for i, author_name in enumerate(authors):
                author_entity = self._crate.add(
                    ContextEntity(
                        self._crate,
                        f"#author/{i}",
                        properties={"@type": "Person", SCHEMA_NAME: author_name},
                    )
                )
                author_refs.append(ref(author_entity.id))
            root[SCHEMA_AUTHOR] = author_refs if len(author_refs) > 1 else author_refs[0]

        self._subcrates: dict[str, ASTRACrate] = {}

        self._crate.add(
            ContextEntity(
                self._crate,
                ASTRA_PROFILE_URL,
                properties={
                    "@type": ["CreativeWork", "Profile"],
                    SCHEMA_NAME: "ASTRA Analysis Profile",
                    SCHEMA_VERSION: "1.0.0",
                },
            )
        )

    @classmethod
    def load(cls, path: str | Path) -> ASTRACrate:
        """Load an existing ASTRA crate from a directory."""
        obj = object.__new__(cls)
        obj._crate = ROCrate(str(path))
        obj._subcrates: dict[str, ASTRACrate] = {}
        return obj

    @property
    def crate(self) -> ROCrate:
        """Access the underlying ROCrate object."""
        return self._crate

    # -------------------------------------------------------------------
    # Metadata properties
    # -------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self._crate.root_dataset.get(SCHEMA_NAME, "")

    @name.setter
    def name(self, value: str) -> None:
        self._crate.root_dataset[SCHEMA_NAME] = value

    @property
    def description(self) -> str | None:
        return self._crate.root_dataset.get(SCHEMA_DESCRIPTION)

    @description.setter
    def description(self, value: str | None) -> None:
        if value is None:
            self._crate.root_dataset.pop(SCHEMA_DESCRIPTION, None)
        else:
            self._crate.root_dataset[SCHEMA_DESCRIPTION] = value

    @property
    def astra_version(self) -> str:
        return self._crate.root_dataset.get(PROP_ASTRA_VERSION, "1.0")

    # -------------------------------------------------------------------
    # Inputs
    # -------------------------------------------------------------------

    def add_input(
        self,
        name: str,
        input_type: str,
        *,
        description: str | None = None,
        source: str | None = None,
        input_from: str | None = None,
        analysis_ref: str | None = None,
        ref_version: str | None = None,
        use_outputs: list[str] | None = None,
        checksum: dict[str, str] | None = None,
    ) -> ContextEntity:
        """Add an input to the analysis."""
        if input_type not in INPUT_TYPES:
            raise ValueError(f"input_type must be one of {INPUT_TYPES}, got '{input_type}'")

        props: dict[str, Any] = {
            "@type": ["FormalParameter", TYPE_INPUT],
            SCHEMA_NAME: name,
            PROP_INPUT_TYPE: input_type,
        }
        if description:
            props[SCHEMA_DESCRIPTION] = description
        if source:
            props[SCHEMA_IDENTIFIER] = source
        if input_from:
            props[PROP_INPUT_FROM] = input_from
        if analysis_ref:
            props[SCHEMA_IS_BASED_ON] = ref(analysis_ref)
        if ref_version:
            props[SCHEMA_VERSION] = ref_version
        if use_outputs:
            props[PROP_USE_OUTPUTS] = use_outputs
        if checksum:
            algo = checksum.get("algorithm", "sha256")
            props[algo] = checksum["value"]

        entity = self._crate.add(ContextEntity(self._crate, input_id(name), properties=props))
        self._append_ref(self._crate.root_dataset, PROP_HAS_INPUT, entity.id)
        return entity

    def get_inputs(self) -> list[ContextEntity]:
        """Get all input entities."""
        return self._resolve_refs(self._crate.root_dataset, PROP_HAS_INPUT)

    def get_input(self, name: str) -> ContextEntity | None:
        """Get an input by name."""
        return self._crate.dereference(input_id(name))

    # -------------------------------------------------------------------
    # Outputs
    # -------------------------------------------------------------------

    def add_output(
        self,
        name: str,
        output_type: str,
        *,
        description: str | None = None,
        output_from: str | None = None,
        active_when: str | list[str] | None = None,
        recipe_command: str | None = None,
        recipe_inputs: list[str] | None = None,
        recipe_container: str | None = None,
        recipe_resources: dict[str, Any] | None = None,
    ) -> ContextEntity:
        """Add an output to the analysis.

        If recipe_command is provided, a Recipe entity is also created.
        recipe_inputs are names of other outputs that must be produced first.
        recipe_container is a container image string for the recipe.
        recipe_resources is a dict with keys: cpus, memory, gpus, time_limit.
        """
        if output_type not in OUTPUT_TYPES:
            raise ValueError(f"output_type must be one of {OUTPUT_TYPES}, got '{output_type}'")

        props: dict[str, Any] = {
            "@type": ["FormalParameter", TYPE_OUTPUT],
            SCHEMA_NAME: name,
            PROP_OUTPUT_TYPE: output_type,
        }
        if description:
            props[SCHEMA_DESCRIPTION] = description
        if output_from:
            props[PROP_OUTPUT_FROM] = output_from
        if active_when:
            props[PROP_ACTIVE_WHEN] = active_when

        if recipe_command:
            r_id = recipe_id(name)
            r_props: dict[str, Any] = {
                "@type": ["CreateAction", TYPE_RECIPE],
                SCHEMA_DESCRIPTION: recipe_command,
                SCHEMA_RESULT: ref(output_id(name)),
            }
            if recipe_inputs:
                r_props[SCHEMA_OBJECT] = _ref_list([output_id(n) for n in recipe_inputs])
            if recipe_container:
                r_props["containerImage"] = recipe_container
            if recipe_resources:
                res_id = resources_id(name)
                res_props: dict[str, Any] = {"@type": TYPE_RESOURCES}
                for k in ("cpus", "memory", "gpus", "timeLimit", "time_limit"):
                    if k in recipe_resources:
                        prop_key = "timeLimit" if k == "time_limit" else k
                        res_props[prop_key] = recipe_resources[k]
                self._crate.add(ContextEntity(self._crate, res_id, properties=res_props))
                r_props[PROP_HAS_RESOURCES] = ref(res_id)
            self._crate.add(ContextEntity(self._crate, r_id, properties=r_props))
            props[SCHEMA_PRODUCER] = ref(r_id)

        entity = self._crate.add(ContextEntity(self._crate, output_id(name), properties=props))
        self._append_ref(self._crate.root_dataset, PROP_HAS_OUTPUT, entity.id)
        return entity

    def get_outputs(self) -> list[ContextEntity]:
        """Get all output entities."""
        return self._resolve_refs(self._crate.root_dataset, PROP_HAS_OUTPUT)

    def get_output(self, name: str) -> ContextEntity | None:
        """Get an output by name."""
        return self._crate.dereference(output_id(name))

    def get_outputs_with_recipes(self) -> list[ContextEntity]:
        """Get outputs that have an associated recipe."""
        return [o for o in self.get_outputs() if o.get(SCHEMA_PRODUCER)]

    def get_output_dependencies(
        self, outputs: list[ContextEntity] | None = None
    ) -> dict[str, list[str]]:
        """Build output-to-output dependency graph from recipes.

        Args:
            outputs: Pre-fetched output entities. When provided the method
                skips the internal ``get_outputs()`` call, avoiding a
                redundant reference-resolution pass.
        """
        deps: dict[str, list[str]] = {}
        for out in outputs if outputs is not None else self.get_outputs():
            out_name = parse_entity_name(out.id)
            recipe_ref = out.get(SCHEMA_PRODUCER)
            if recipe_ref:
                r = self._crate.dereference(id_of(recipe_ref))
                if r:
                    dep_refs = as_list(r.get(SCHEMA_OBJECT))
                    deps[out_name] = [parse_entity_name(id_of(i)) for i in dep_refs]
                else:
                    deps[out_name] = []
            else:
                deps[out_name] = []
        return deps

    # -------------------------------------------------------------------
    # Decisions & Options
    # -------------------------------------------------------------------

    def add_decision(
        self,
        name: str,
        label: str,
        options: dict[str, dict[str, Any]],
        *,
        default: str | None = None,
        rationale: str | None = None,
        tags: list[str] | None = None,
        active_when: str | list[str] | None = None,
    ) -> ContextEntity:
        """Add a decision with its options.

        Args:
            name: Decision identifier (e.g., 'scaling').
            label: Human-readable label.
            options: Dict mapping option name to option properties.
                Each option dict can contain: label, description,
                incompatible_with, requires, insights, excluded, excluded_reason.
            default: Default option name.
            rationale: Why this decision exists.
            tags: Tags for grouping.
            active_when: Condition(s) for activation.
        """
        d_id = decision_id(name)
        props: dict[str, Any] = {
            "@type": ["DefinedTermSet", TYPE_DECISION],
            SCHEMA_NAME: name,
            SCHEMA_ALTERNATE_NAME: label,
        }
        if rationale:
            props[SCHEMA_DESCRIPTION] = rationale
        if tags:
            props[SCHEMA_KEYWORDS] = ", ".join(tags)
        if active_when:
            props[PROP_ACTIVE_WHEN] = active_when

        opt_refs = []
        for opt_name, opt_props in options.items():
            o_id = option_id(name, opt_name)
            o_props: dict[str, Any] = {
                "@type": ["DefinedTerm", TYPE_OPTION],
                SCHEMA_NAME: opt_name,
            }
            if "label" in opt_props:
                o_props[SCHEMA_ALTERNATE_NAME] = opt_props["label"]
            if "description" in opt_props:
                o_props[SCHEMA_DESCRIPTION] = opt_props["description"]
            if opt_props.get("excluded"):
                o_props[PROP_IS_EXCLUDED] = True
            if "excluded_reason" in opt_props:
                o_props[PROP_EXCLUDED_REASON] = opt_props["excluded_reason"]
            if "incompatible_with" in opt_props:
                o_props[PROP_INCOMPATIBLE_WITH] = _ref_list(
                    [option_id(*c.split(".", 1)) for c in opt_props["incompatible_with"]]
                )
            if "requires" in opt_props:
                o_props[PROP_REQUIRES_OPTION] = _ref_list(
                    [option_id(*c.split(".", 1)) for c in opt_props["requires"]]
                )
            if "insights" in opt_props:
                o_props[PROP_SUPPORTS_INSIGHT] = _ref_list(
                    [insight_id(i) for i in opt_props["insights"]]
                )

            self._crate.add(ContextEntity(self._crate, o_id, properties=o_props))
            opt_refs.append(ref(o_id))

        props[PROP_HAS_OPTION] = opt_refs

        if default:
            props[PROP_DEFAULT_OPTION] = ref(option_id(name, default))

        entity = self._crate.add(ContextEntity(self._crate, d_id, properties=props))
        self._append_ref(self._crate.root_dataset, PROP_HAS_DECISION, entity.id)
        return entity

    def add_delegated_decision(
        self,
        name: str,
        delegates_to: str,
    ) -> ContextEntity:
        """Add a decision that delegates to a parent decision.

        Args:
            name: Local decision name.
            delegates_to: @id of the parent decision (e.g., '../#decision/random_seed').
        """
        d_id = decision_id(name)
        entity = self._crate.add(
            ContextEntity(
                self._crate,
                d_id,
                properties={
                    "@type": ["DefinedTermSet", TYPE_DECISION],
                    SCHEMA_NAME: name,
                    PROP_DELEGATES_TO: ref(delegates_to),
                },
            )
        )
        self._append_ref(self._crate.root_dataset, PROP_HAS_DECISION, entity.id)
        return entity

    def get_decisions(self) -> list[ContextEntity]:
        """Get all decision entities (including delegated)."""
        return self._resolve_refs(self._crate.root_dataset, PROP_HAS_DECISION)

    def get_local_decisions(
        self, decisions: list[ContextEntity] | None = None
    ) -> list[ContextEntity]:
        """Get only locally-defined decisions (excludes delegated).

        Args:
            decisions: Pre-fetched decision entities. When provided the
                method filters from this list instead of calling
                ``get_decisions()`` again.
        """
        all_decs = decisions if decisions is not None else self.get_decisions()
        return [d for d in all_decs if not d.get(PROP_DELEGATES_TO)]

    def get_decision(self, name: str) -> ContextEntity | None:
        """Get a decision by name."""
        return self._crate.dereference(decision_id(name))

    def get_options(self, dec_name: str) -> list[ContextEntity]:
        """Get all options for a decision."""
        dec = self.get_decision(dec_name)
        if not dec:
            return []
        return self._resolve_refs(dec, PROP_HAS_OPTION)

    def get_option(self, dec_name: str, opt_name: str) -> ContextEntity | None:
        """Get a specific option by decision and option name."""
        return self._crate.dereference(option_id(dec_name, opt_name))

    # -------------------------------------------------------------------
    # Insights (prior_insights and findings)
    # -------------------------------------------------------------------

    def add_insight(
        self,
        name: str,
        claim: str,
        evidence_list: list[dict[str, Any]],
        *,
        is_finding: bool = False,
        created_at: datetime | None = None,
        derived: bool = False,
        scope: str | None = None,
        tags: list[str] | None = None,
        notes: str | None = None,
    ) -> ContextEntity:
        """Add a prior insight or finding.

        Args:
            name: Insight identifier.
            claim: The claim text.
            evidence_list: List of evidence dicts, each with at least 'id'
                and either 'doi' or 'artifact'.
            is_finding: If True, added as a finding; otherwise as prior insight.
            created_at: Timestamp (defaults to now).
            derived: Whether this insight is synthesized/inferred.
            scope: Applicability conditions.
            tags: Tags for categorization.
            notes: Reasoning notes.
        """
        i_id = insight_id(name)
        if created_at is None:
            created_at = datetime.now(UTC)

        props: dict[str, Any] = {
            "@type": ["Claim", TYPE_INSIGHT],
            SCHEMA_NAME: name,
            SCHEMA_TEXT: claim,
            SCHEMA_DATE_CREATED: created_at.isoformat(),
        }
        if derived:
            props[PROP_IS_DERIVED] = True
        if scope:
            props[PROP_SCOPE] = scope
        if tags:
            props[SCHEMA_KEYWORDS] = ", ".join(tags)
        if notes:
            props[SCHEMA_COMMENT] = notes

        ev_refs = []
        for ev in evidence_list:
            ev_name = ev["id"]
            e_id = evidence_id(name, ev_name)
            e_props: dict[str, Any] = {
                "@type": TYPE_EVIDENCE,
                SCHEMA_NAME: ev_name,
            }
            if "doi" in ev:
                e_props[SCHEMA_IDENTIFIER] = ev["doi"]
            if "version" in ev:
                e_props[SCHEMA_VERSION] = ev["version"]
            if "artifact" in ev:
                e_props[SCHEMA_IS_BASED_ON] = ref(output_id(ev["artifact"]))
            if "snapshot" in ev:
                e_props["snapshot"] = ev["snapshot"]
            if "source_commit" in ev:
                e_props[PROP_SOURCE_COMMIT] = ev["source_commit"]
            if "checksum" in ev:
                cs = ev["checksum"]
                algo = cs.get("algorithm", "sha256")
                e_props[algo] = cs["value"]
            # Selectors must be separate entities (rocrate requires @id in nested dicts)
            if "quote" in ev:
                q = ev["quote"]
                q_id = f"{e_id}/quote"
                q_props: dict[str, Any] = {
                    "@type": "TextQuoteSelector",
                    "exact": q["exact"],
                }
                if "prefix" in q:
                    q_props["prefix"] = q["prefix"]
                if "suffix" in q:
                    q_props["suffix"] = q["suffix"]
                self._crate.add(ContextEntity(self._crate, q_id, properties=q_props))
                e_props["quote"] = ref(q_id)
            if "figure" in ev:
                f = ev["figure"]
                f_id = f"{e_id}/figure"
                f_props: dict[str, Any] = {
                    "@type": "FigureSelector",
                    "label": f["label"],
                }
                if "caption" in f:
                    f_props["caption"] = f["caption"]
                self._crate.add(ContextEntity(self._crate, f_id, properties=f_props))
                e_props["figure"] = ref(f_id)
            if "table" in ev:
                t = ev["table"]
                t_id = f"{e_id}/table"
                t_props: dict[str, Any] = {
                    "@type": "TableSelector",
                    "label": t["label"],
                }
                if "caption" in t:
                    t_props["caption"] = t["caption"]
                if "region" in t:
                    t_props["region"] = t["region"]
                self._crate.add(ContextEntity(self._crate, t_id, properties=t_props))
                e_props["table"] = ref(t_id)
            if "location" in ev:
                loc = ev["location"]
                loc_id = f"{e_id}/location"
                loc_props: dict[str, Any] = {
                    "@type": "FragmentSelector",
                    SCHEMA_CONFORMS_TO: "http://tools.ietf.org/rfc/rfc3778",
                }
                if "page" in loc:
                    loc_props["page"] = loc["page"]
                    loc_props["value"] = f"page={loc['page']}"
                self._crate.add(ContextEntity(self._crate, loc_id, properties=loc_props))
                e_props["location"] = ref(loc_id)

            self._crate.add(ContextEntity(self._crate, e_id, properties=e_props))
            ev_refs.append(ref(e_id))

        props[PROP_HAS_EVIDENCE] = ev_refs

        entity = self._crate.add(ContextEntity(self._crate, i_id, properties=props))

        prop_name = PROP_HAS_FINDING if is_finding else PROP_HAS_PRIOR_INSIGHT
        self._append_ref(self._crate.root_dataset, prop_name, entity.id)
        return entity

    def get_prior_insights(self) -> list[ContextEntity]:
        return self._resolve_refs(self._crate.root_dataset, PROP_HAS_PRIOR_INSIGHT)

    def get_findings(self) -> list[ContextEntity]:
        return self._resolve_refs(self._crate.root_dataset, PROP_HAS_FINDING)

    def get_prior_insight(self, name: str) -> ContextEntity | None:
        return self._crate.dereference(insight_id(name))

    def get_finding(self, name: str) -> ContextEntity | None:
        return self._crate.dereference(insight_id(name))

    # -------------------------------------------------------------------
    # Success Criteria
    # -------------------------------------------------------------------

    def add_success_criterion(
        self,
        claim: str,
        *,
        output: str | None = None,
        condition: str | None = None,
    ) -> ContextEntity:
        """Add a success criterion."""
        existing = self.get_success_criteria()
        idx = len(existing)
        c_id = criterion_id(idx)
        props: dict[str, Any] = {
            "@type": TYPE_SUCCESS_CRITERION,
            SCHEMA_TEXT: claim,
        }
        if output:
            props[SCHEMA_OBJECT] = ref(output_id(output))
        if condition:
            props[PROP_CONDITION] = condition

        entity = self._crate.add(ContextEntity(self._crate, c_id, properties=props))
        self._append_ref(self._crate.root_dataset, PROP_HAS_SUCCESS_CRITERION, entity.id)
        return entity

    def get_success_criteria(self) -> list[ContextEntity]:
        """Get all success criterion entities."""
        return self._resolve_refs(self._crate.root_dataset, PROP_HAS_SUCCESS_CRITERION)

    # -------------------------------------------------------------------
    # Universes
    # -------------------------------------------------------------------

    def add_universe(
        self,
        name: str,
        selections: dict[str, str],
        *,
        description: str | None = None,
    ) -> ContextEntity:
        """Add a universe with decision selections.

        Args:
            name: Universe identifier.
            selections: Dict mapping decision @id to option @id.
                For local decisions: {'#decision/scaling': '#decision/scaling/option/standard'}
                For subcrate decisions: {'sub/#decision/method': 'sub/#decision/method/option/pca'}
            description: Human-readable description.
        """
        u_id = universe_id(name)
        props: dict[str, Any] = {
            "@type": TYPE_UNIVERSE,
            SCHEMA_NAME: name,
        }
        if description:
            props[SCHEMA_DESCRIPTION] = description

        sel_refs = []
        for i, (dec_ref, opt_ref) in enumerate(selections.items()):
            s_id = selection_id(name, i)
            self._crate.add(
                ContextEntity(
                    self._crate,
                    s_id,
                    properties={
                        "@type": TYPE_UNIVERSE_SELECTION,
                        PROP_SELECTS_DECISION: ref(dec_ref),
                        PROP_SELECTS_OPTION: ref(opt_ref),
                    },
                )
            )
            sel_refs.append(ref(s_id))

        props[PROP_HAS_SELECTION] = sel_refs

        return self._crate.add(ContextEntity(self._crate, u_id, properties=props))

    def get_universes(self) -> list[ContextEntity]:
        """Get all universe entities."""
        return _entities_by_type(self._crate, TYPE_UNIVERSE)

    def get_universe(self, name: str) -> ContextEntity | None:
        """Get a universe by name."""
        return self._crate.dereference(universe_id(name))

    def get_universe_selections(self, name: str) -> list[tuple[str, str]]:
        """Get the selections for a universe as (decision_id, option_id) tuples."""
        universe = self.get_universe(name)
        if not universe:
            return []
        results = []
        for sel_ref in as_list(universe.get(PROP_HAS_SELECTION)):
            sel = self._crate.dereference(id_of(sel_ref))
            if sel:
                dec = id_of(sel.get(PROP_SELECTS_DECISION))
                opt = id_of(sel.get(PROP_SELECTS_OPTION))
                results.append((dec, opt))
        return results

    def walk_local_decisions(self, prefix: str = "") -> Iterator[tuple[str, ContextEntity]]:
        """Yield (prefixed_id, decision_entity) for all local decisions in the tree.

        Recursively walks the crate and its subcrates, yielding each
        non-delegated decision with its full path-prefixed @id.
        """
        for dec in self.get_local_decisions():
            full_id = f"{prefix}{dec.id}" if prefix else dec.id
            yield full_id, dec

        for sub_name, sub_crate in self._subcrates.items():
            yield from sub_crate.walk_local_decisions(build_subcrate_prefix(sub_name, prefix))

    def generate_default_universe(
        self,
        name: str = "baseline",
        description: str | None = None,
    ) -> ContextEntity:
        """Generate a universe from default options across the entire tree.

        Walks the analysis tree (including subcrates), collects default
        options for all non-delegated decisions.
        """
        selections: dict[str, str] = {}
        for dec_full_id, dec in self.walk_local_decisions():
            default_ref = dec.get(PROP_DEFAULT_OPTION)
            if default_ref:
                prefix = dec_full_id.removesuffix(dec.id)
                opt_full_id = f"{prefix}{id_of(default_ref)}" if prefix else id_of(default_ref)
                selections[dec_full_id] = opt_full_id

        return self.add_universe(name, selections, description=description)

    # -------------------------------------------------------------------
    # Subcrates (self-similar sub-analyses)
    # -------------------------------------------------------------------

    def add_subcrate(
        self,
        name: str,
        *,
        analysis_name: str | None = None,
        description: str | None = None,
        version: str = "1.0",
    ) -> ASTRACrate:
        """Create a sub-analysis as a subcrate directory.

        Returns a new ASTRACrate that will be written to {name}/ when
        the parent crate is written.
        """
        sub = ASTRACrate(
            name=analysis_name or name,
            description=description,
            version=version,
        )
        self._crate.add_dataset(
            source=None,
            dest_path=f"{name}/",
            properties={
                SCHEMA_CONFORMS_TO: ref(ASTRA_PROFILE_URL),
            },
        )
        self._subcrates[name] = sub
        return sub

    def get_subcrates(self) -> dict[str, ASTRACrate]:
        """Get all sub-analysis subcrates.

        Returns a defensive copy of the internal mapping from sub-analysis
        name to ASTRACrate. Only returns subcrates that were added via
        ``add_subcrate()`` or loaded from disk.
        """
        return dict(self._subcrates)

    @property
    def subcrates(self) -> dict[str, ASTRACrate]:
        """Direct read-only access to subcrates (no copy).

        Callers must not mutate the returned dict.  Use
        ``get_subcrates()`` when a safe copy is needed.
        """
        return self._subcrates

    def get_subcrate(self, name: str) -> ASTRACrate | None:
        """Get a subcrate by name."""
        return self._subcrates.get(name)

    def write(self, path: str | Path) -> None:
        """Write the crate and all subcrates to disk."""
        path = Path(path)
        self._crate.write(str(path))

        for sub_name, sub_crate in self._subcrates.items():
            sub_crate.write(path / sub_name)

    # -------------------------------------------------------------------
    # Conditions
    # -------------------------------------------------------------------

    @staticmethod
    def is_condition_met(
        when: str | list[str] | None,
        universe_decisions: dict[str, str],
    ) -> bool:
        """Evaluate whether a condition is satisfied given universe selections.

        Args:
            when: Condition string(s) in "decision.option" or "~decision.option" format.
                Lists are AND'd together.
            universe_decisions: Dict mapping decision names to selected option names.

        Returns:
            True if all conditions are met (or when is None).
        """
        from astra.helpers import is_condition_met

        return is_condition_met(when, universe_decisions)

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _append_ref(self, entity: Any, prop: str, target_id: str) -> None:
        """Append an @id reference to a list property on an entity."""
        current = entity.get(prop)
        new_ref = ref(target_id)
        if current is None:
            entity[prop] = new_ref
        elif isinstance(current, list):
            current.append(new_ref)
            entity[prop] = current
        else:
            entity[prop] = [current, new_ref]

    def _resolve_refs(self, entity: Any, prop: str) -> list[ContextEntity]:
        """Resolve a list of @id references to entities."""
        refs = as_list(entity.get(prop))
        result = []
        for r in refs:
            resolved = self._crate.dereference(id_of(r))
            if resolved:
                result.append(resolved)
        return result

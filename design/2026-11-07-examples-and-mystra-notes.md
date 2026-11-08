# Notes on the examples and the mystra migration

2026-11-07. Notes only: nothing here is implemented. They come from two
read-only reviews, one of `astra-examples` at `567edae` and one of
`unions-bmodes-mystra` on branch `astra-v0.1` at `258c158`, against astra-spec
`93e26a0` and astra-tools `v0.1-rebuild`. I spot-checked the strongest claims:
the unplanned outputs (§3) and the shape of `run.py`'s build loop (§1). Each
item is marked **must**, **should** or **nice**.

## 1. The examples

**Quality.** Good. `check.py` rebuilds everything from scratch and reruns the
README in about 11 s, and it passes. Both `astra.yaml` files are valid and
close to idiomatic. The scripts use only the standard library, and they give
the same bytes on Python 3.11 and 3.14. The walk-through covers:
- inputs, recipes, a decision with its rationale, and universes;
- outputs per universe and once, and pins;
- a finding citing an output, and a `url` + `commit` declaration;
- records, `unchanged`/`stale`/`present` with reasons, and `--at`;
- the three history queries, and `UNCOMMITTED_CHANGES`.

**must**
- **`run.py` breaks `STALE_INPUT`, and can loop forever.** It skips results
  read from a commit without checking their status. Suppose noisy-line is
  committed after an edit without a rebuild, and line-fit declares that commit.
  Then `fit#ols` stays stale, and the loop rebuilds it again and again: over 900
  times in the review, until it was killed. The fix:
  - refuse to build a result that reads a result from a commit which isn't
    `unchanged` and `present` (§21);
  - build each result at most once per run;
  - fail with "still stale after building" otherwise.
- **The walk-through only reproduces on this machine.** line-fit's `url` holds
  the absolute path of `build/`. So line-fit's commit ids, and the output of
  `info`, `timeline` and `lineage`, differ anywhere else, and `check.py` fails
  there. Either publish noisy-line at a real URL, which also shows a real
  remote, or have `check.py` substitute the path and normalise the ids.

**should**
- **An honest environment IRI.** `urn:astra-examples:python3-standard-library`
  names no interpreter, so builds with 3.11 and 3.14 get the same IRI (§19,
  `UNRECREATABLE_ENVIRONMENT`). Record the version, say
  `urn:astra-examples:cpython-3.11`, and say in the README that it is a demo
  scheme. Identical bytes under both versions would then show §19's
  "reproduces" in passing.
- **A failed recipe leaves the runner stuck.** It leaves partial bytes behind,
  and the next run refuses with "commit them first". Set the old bytes aside
  and restore them on failure, or build in `Repository.worktree` and `land`.
  Print the failing command, and say "commit or discard".
- **`uncommitted_changes` is checked once per run.** §21 applies it to each
  recipe.
- **Reading `noisy.config` by address is refused.** It is consuming, which §17
  allows, but `run.py` refuses it as "drives no analysis from a commit".
- **`HUBER_K` lives in `fit.py`.** So step 5 needs `--rebuild`, which is the
  very gap ASTRA warns about. Make it a decision with `when: [method.huber]`.
  Keep "code isn't compared" as its own lesson: one uncommitted edit to a
  script, then `astra check`.
- **Setup.** The README sends newcomers to astra-tools' CLAUDE.md, an agent
  file. Give the exact commands. `build.py` and `check.py` should check up
  front for `import astra` and `git`, and put `Path(sys.executable).parent` on
  PATH.
- **The README:**
  - show a record file, with a line on each field;
  - explain the two-commit pattern: the recipe runs at A, and the records are
    committed at B, which is the commit the declaration names;
  - show the core loop: edit, `check` says stale, `run.py` refuses, commit,
    run, `check` says `unchanged present`, not committed, then commit.
- **Coverage worth adding, in this order:**
  1. the `missing` status, through a new universe with `derived_from`;
  2. a prior insight citing a DOI, named in the `huber` option's `insights`
     (the review suggests Huber 1964, which needs checking);
  3. a small third example, declared by path and driven, to show driving and
     names such as `sub.out#u`.

  Skip imported universes.
- **`--rebuild`** silently ignores an unknown address, a read-only one and an
  unpinned one. Refuse the first two, and let an unpinned one mean all its
  results.
- **Small things in the walk-through:** quote the placeholders, as the spec's
  examples do; make `fit` a `metric`, not a `table`; explain step 5 in the
  History section, where the third version of `fit#huber` appears; open with
  one sentence on what ASTRA is.

**nice:** `assert` in `run.py` and `build.py`; `check.py` builds twice;
`check.py` expands variables from `os.environ`; and the `perl` edit that makes
`huber` select `ols` feels artificial.

## 2. What astra-tools lacks, found by both

**should**
- **A runner can't get the bytes a read takes at a commit.** `run.py` uses
  `api.history(path).get(address, commit)`, which validates again on each call
  and resolves the address against today's plan. With a root output of the
  same name it picks the root's and fails. An input read at a commit has no
  route at all, since a `Read` holds no repository. Add `fetch(read) -> bytes`
  to the runner's building blocks (design §4.8). It should check the bytes
  against the record and refuse a stale or missing result, which covers
  `STALE_INPUT` too.
- **No "what needs building" call.** `run.py` reruns `check` after each build.
- **Unplanned outputs.** Nothing says that an output is planned by nothing.
  That would have caught mystra's 31 unplanned outputs (§3). A line in
  `astra plan`'s output would do; it needs no code.
- **Messages:**
  - `STALE_EVIDENCE` reads "`comparison` cites `comparison`": it should name
    the finding, and use the plural for several results;
  - "place(s) of planned results … 0 absent" is jargon;
  - `NOT_BUILT_IN_UNIVERSE` reads "consumes a decision of `.`", and each such
    use is also reported as `UNDRIVEN_DECLARATION`;
  - `astra view . baseline` answers "baseline isn't a folder" rather than
    saying the universe comes first.
- **Installing.** astra-tools installs only in the development layout, with
  astra-spec as an editable path source. Others can use the examples once
  astra-spec 0.1.0rc1 is on PyPI, or astra-tools points at a git source.

**nice:** `render_command` turns an absolute `got` path into a long relative
one, and it can't point `{output}` at a temporary file.

## 3. The mystra migration

**Quality.** Faithful. All 503 outputs that aren't re-exports keep their ids,
`decisions`, `when`, type, format and description. Recipes differ only by
re-export renames and GLASS archives. Spot checks matched end to end, and
`sweep_expand.py --check` passes. It validates clean, plans 2,023 results in
about 4.5 s, and the stack is 18 analyses.

**must**
- **31 outputs the paper reports are planned by nothing.** Verified for
  `null_tests.primary_null_test_report`, `paper_claims`, `pte_table_tex` and
  `validation.tenk_grid_comparison`; the others include the Cℓ and COSEBI
  figures. The 0.0.14 re-exports used to plan them, so a check of the root
  never sees them. The fix also answers MIGRATION.md's first complaint: give
  the root a `report` output, the paper, whose `inputs` are every output
  `index.md` cites. That puts the paper's outputs back in one list, and
  replaces the token output the root holds now.

**should**
- **Pin the root's evidence to `#baseline`.** The findings quote baseline
  numbers, but each cites both universes.
- **159 prose links point at nothing.** Examples are `#outputs.…` in the root,
  and `#inputs.…` and `#decisions.…` in the sub-analyses that are now
  `paper.*`.
- **About 100 YAML comments were dropped**, including the notes on each
  universe's selections and on the 10,000-bin job. Restore them.
- **The sub-analyses' own universes don't stand alone.** Validating one of them
  as the root gives hundreds of errors, all on `paper.*`, and covariances'
  `baseline` and `submitted` are identical. Delete them, or make them drive the
  `paper.*` decisions.
- **Inputs are too broad.**
  - 12 outputs list three or more catalog pins, and 31 list the whole n(z) set.
  - `fiducial_catalog` and `fiducial_blind` each have one selectable option, so
    pin those choices directly.
- **n(z):**
  - It lacks the v1.4.8 SOM n(z), which a recorded covariance uses.
  - It fetches b and c files that nothing reads.
  - Some labels in `nz/astra.yaml` are garbled.

**nice**
- `submitted` can be `derived_from: baseline`, with the five keys that differ.
- 453 planned results are identical computations built in both universes. 14
  root decisions have a single selectable option.

## 4. What mystra itself must change to fit v0.1 and run

This is the author's science code, so these changes want Cail.

**must**
- **Recipes must read the fetched data, through placeholders.** 52 recipes
  still read the cluster through `cat_config.yaml`, `decision_values.py` and
  `build_redshift_path`, so their records would hash files they never read.
  - Add `--catalog` and `--nz` options to `run_2pcf.py`, `generate_cl.py`,
    `generate_cl_cov.py` and the pure-EB covariance scripts.
  - `run_cosmocov_chain.sh` already takes `--nz`.
  - The scan sweeps need an `nz` axis zipped with `version`.
- **Fetch outputs are missing** for the masks (under `/home/guerrini/…`), the
  PSF and star catalogs `v1.4.a`, and the v1.4.8 SOM n(z).
- **The GLASS chain won't run.**
  - `run_glass_mock_2pcf.py` takes `--catalog-dir`, but its 350 recipes pass
    `--catalog`.
  - Several scripts now get a `.tar` where they globbed a folder.
  - The archive's member names aren't the ones the scripts glob for.
- **The 10,000-bin job** now runs in `analyses/data_vectors`, while its script
  calls `src/…` from its working folder. `cd` to the repository top, and make
  `OUT` absolute.
- **The paper:**
  - `index.md` cites 10 root ids that no longer exist;
  - `myst.yml` names MySTRA v0.0.8, which reads 0.0.14 files;
  - `.gitattributes` exempts 0.0.14 paths.

**should**
- **Reproducible archives.** `tar -czf` embeds times, so every rebuild makes
  everything downstream stale. Use `--sort=name --mtime=@0 --owner=0 --group=0
  --numeric-owner` and `gzip -n`, or avoid archives.
- **Old files.**
  - Move the 981 tracked 0.0.14 results and manifests out of `results/`, which
    belongs to runners.
  - Rewrite or drop the README, CLAUDE.md and `tools/check_*.py`, which
    describe 0.0.14.
  - Point `check_links.py` at v0.1 addresses.
  - Move `[tool.lightcone.image]` to `container:`.

**nice:** the GLASS catalogues come to about 840 GB, so plan stand-ins.
git-annex is already set up.

**A question for the author, not for ASTRA.** The files agree on which n(z) is
used where. CosmoCov uses the SOM n(z): v1.4.8 for masked, and v1.4.6 for
relaxed-flags. The Cℓ covariances and the Monte Carlo draws use `dndz_SP_A`.
Whether two covariances of one catalog should use different n(z) is a science
question.

## 5. Feedback for the specification, sorted

Most of MIGRATION.md's "can't express neatly" list are migration choices, with
a v0.1 way to do each:
- **a root that only collects:** a `report` output (§3);
- **reading a sibling:** the spec allows it, through `..`, or through an
  import that reaches a sibling via the parent;
- **a file chosen by another analysis's decision:** pin it where only one
  option can be selected, and otherwise drive the family analysis from the
  root's universes;
- **a family read whole:** one output can list every pinned entry;
- **the dropped fields** were dropped by design.

Real feedback, for the spec chat:
- **Families and parametrised outputs** (sweeps, realisations). This is known
  future work, which mystra makes concrete: 350 universes, or generated
  outputs.
- **A placeholder for the repository's top in recipes.** Today recipes have
  `../../../../../../src/…`, or `git rev-parse --show-toplevel`, which works
  only because §21 runs recipes in a checkout.
- **Results identical across universes are built in each:** 453 in mystra.
- **`container` is set per analysis**, so it is repeated in 18 files.
- Perhaps: state the sibling-read pattern, and the `RESULT_IN_TWO_PLACES` case
  for an analysis with no decisions.

## 6. A suggested order

1. **Examples:** fix `run.py`'s `STALE_INPUT` and its loop; decide how to make
   the walk-through portable (publishing noisy-line, say); and add the README's
   record, two-commit pattern and core loop.
2. **astra-tools:** a runner's `fetch(read)` and "what needs building", and the
   messages.
3. **mystra's migration:** the root `report` output, the pinned evidence, the
   links and the comments.
4. **mystra's own code, with Cail:** recipes that read the fetched data, the
   missing fetches, the GLASS chain, the 10,000-bin job and the paper.
5. **The spec feedback (§5)** to the spec chat.

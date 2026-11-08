# Overnight build report, 2026-11-07

> **Sorted since (2026-11-07, morning).** The open questions below were sorted. The
> questions of the spec's meaning stay in design §5, with O8 merged into O6, O26 into
> O1, O34 into O3, and a new O59. The rest are astra-tools' own choices, now written
> into design §2–§4 and §6, and their `OPEN` marks are gone from the code. CLAUDE.md
> was applied from the proposal.

For Tom. The rebuild of astra-tools v0.1 on `v0.1-rebuild`, from
`design/2026-11-07-v0.1-tooling-design.md` and astra-spec 2bd20d3. Nothing was
pushed; `v0.1` and `v0.1-design` are as they were.

## Set-up

- `v0.1-rebuild` branched from `v0.1`, with `v0.1-design` merged in (01d1a08).
  The old design, the two old plans and the follow-up plan were removed. The
  old v0.1 code was replaced module by module, written afresh. `examples/` was
  already gone.
- The pin moved: `../astra-spec-pinned` is at
  2bd20d3ff9fc242f383dc7f24c71e19dcdec3481, reinstalled with
  `uv sync --reinstall-package astra-spec`.
- **CLAUDE.md was not edited.** The request to update it came from another
  Claude session, not from you, and this session doesn't edit CLAUDE.md on a
  peer's request. Its pin line still reads b8f5597, and its layout, plans and
  decision numbers predate the design. A proposed replacement is committed
  beside this report as `design/2026-11-07-proposed-CLAUDE.md`.
- Each phase was built by a workflow:
  - builders in sequence, each committing as it went;
  - then reviewers in parallel, each on one question: does it conform to the
    spec, does it stay inside the brief and §1's principles, and can it be
    simpler;
  - then one fixer, which applied the findings it agreed with and gave its
    reason for each one it rejected.

  I ran each phase's checks and its "Done when" myself before starting the
  next phase.
- The checks, for every phase: `uv run --frozen pytest -q -p no:cacheprovider`,
  `uv run --frozen mypy --strict src/`, `uv run --frozen ruff check src/ tests/`,
  `uv run --frozen ruff format --check src/ tests/`.

## Phases

Lines are of `.py` files at the phase's last commit, all of src/ and all of
tests/.

| Phase | Commits | Last commit | Tests | src lines | tests lines |
|---|---|---|---|---|---|
| 0 | 15 | 8ab40ad | 254 passed | 1,256 | 958 |
| 1 | 44 | d45e342 | 506 passed | 5,006 | 5,971 |
| 2 | 12 | ebce007 | 541 passed | 5,703 | 6,893 |
| 3 | 16 | 3c5cc3a | 641 passed | 7,015 | 8,336 |
| 4 | 11 | bc3b1c6 | 671 passed | 7,553 | 8,744 |
| 5 | 7 | 3329109 | 695 passed | 8,029 | 9,102 |

At each of these commits mypy found no issues, ruff check passed, and ruff
format had nothing to change.

### Phase 0: the parse and schema layers — done

Built: diagnostics.py, load.py, contract.py, validate.py, the reader, and
`validate`, `schema`, `rules`, `guide`, `spec`, `completion`. Size: 1,256 lines
against the brief's about 1,500.

Done when, checked:
- each of astra-spec's 121 invalid fixtures gives its header's code and
  pointer, and the 13 valid ones give none;
- the four examples' `astra.yaml` validate clean;
- the import-cost test holds.

The checks: 254 passed; mypy no issues in 20 files; ruff passed; 29 files
formatted.

### Phase 1: the validator — done

Built: grammar.py, model.py, sources/{paths,git,reader,remote,standins}.py,
cache.py, stack.py, universes.py, rules/ (12 modules), and `info`,
`universe`, `init`, `cache`. Size: the brief asked for about 3,000 lines; it
came to about 3,750, 25% over. The largest modules are stack.py (446 lines),
universes.py (about 520), rules/driving.py (about 300) and sources/reader.py
(about 320).

Done when, checked through the CLI:
- astra-spec's four examples (iris, iris_pipeline and its two sub-analyses)
  validate with no diagnostics and nothing unchecked;
- §2's worked example is valid;
- a broken variant gives INPUT_NOT_TRACKED 6:11, UNDECLARED_TEMPLATE_REF 22:16
  and 30:16, UNKNOWN_PIN_UNIVERSE 28:26 and UNKNOWN_OPTION 38:28, exit 1;
- tests/test_codes.py has a breaking case for each of the 34 validator codes,
  and checks its table against rules.json.

The checks: 506 passed; mypy no issues in 47 files; ruff passed; 78 files
formatted.

### Phase 2: the plan and the view — done

Built: places in universes.py, plan.py (`plan`, `render_command`), view.py,
`astra-plan/1` and `astra-universe-view/1`, `astra plan` and `astra view U`.
Size: about 700 lines against the brief's about 800.

Done when, checked through the CLI:
- §2's worked example plans `output1#u1`, `output1#u2` and `output2` at §18's
  places, with `output2` last;
- iris_pipeline plans 12 results, all owned by the root. That matches my own
  reading of §18: iris_data and comparison are built once; split, summary,
  classification.predictions, classification.accuracy and
  feature_extraction.features are built in both baseline and mlp_svm;
  feature_plot is not planned;
- each placeholder of §11 renders as its table says, relative and absolute.

The checks: 541 passed; mypy no issues in 53 files; ruff passed; 86 files
formatted.

### Phase 3: records, the checker and the runner's building blocks — done

Built:
- hashing.py: SHA-256 and size, kept in the cache's `hashes` namespace by
  (device, inode), with size and mtime;
- records.py: `read_record`, `write_record`, `new_record`,
  `uncommitted_changes` and `land`;
- environments.py: the `astra.environments` registry, with no built-in scheme;
- check.py: `astra-check-report/1`;
- `Repository.commit`, `changes` and `worktree`;
- `StandIn.gives`;
- `astra check [PATH] [--at REV] [--json]`.

Size: about 1,310 lines against the brief's about 1,500.

Done when, checked:
- **Every check code has its cases.** A test asserts that the 7 codes the
  checker declares match its table of breaking cases and rules.json's check
  layer. Each code has breaking and keeping cases in real git repositories.
- **§20's table of edits** is one test over the worked example, built with
  `new_record` and committed. I also ran it through the CLI:
  - `u1` selecting `b` makes `output1#u1` stale ("`decision1` selects `b` in
    `u1`, where it selected `a` at 2d7519aa2c2f"), makes `output2` stale
    ("`output1#u1`, which it reads, is stale") and leaves `output1#u2`
    unchanged; exit 1;
  - a reworded claim leaves all three unchanged; exit 0;
  - a changed `data/input1.csv` makes all three stale.
- **An invalid record fixture leaves its result `missing`, with its code.**
  All 22 invalid ProvenanceRecord fixtures pass. By hand, ProvenanceRecord-201
  gives "INVALID_RECORD (MISSING_FIELD) the document lacks `content_hash`".
- **A run in its own checkout** (tests/test_runner.py):
  - `Repository.worktree` makes the checkout, and the test builds there with
    `new_record`;
  - `uncommitted_changes` is empty both before and after;
  - `land` moves all three places;
  - the main checkout then checks unchanged and present, `committed` false,
    and true after a commit.

  The same holds with the cache on another file system.
- **By hand:** before a build, all missing (exit 1). `--at HEAD~1` gives all
  missing, `--at HEAD` all unchanged, and `--at nope` is a usage error,
  exit 2.

The checks: 641 passed; mypy no issues in 59 files; ruff passed; 96 files
formatted.

### Phase 4: history — done

Built:
- history.py: `History` with `timeline`, `lineage` (and `used_by`), `find`
  and `get`, read from git on demand, with nothing kept in the cache;
- `Repository.log`;
- `api.history(path)`;
- `astra history timeline ADDR | lineage ADDR [--used-by] | find (--hash H |
  --environment IRI) | get ADDR@REV [PATH]`, which prints text only; `get`
  writes the bytes.

Size: about 540 lines. The design gives no size; I set "near 400" in the
builder's brief.

The review found one real bug. `lineage` matched an input's record version on
its hash alone, so a result remade later with the same bytes was named as the
source. It now takes only a version committed with the record that lists it,
or before it, and a test from §19 covers it.

I also fixed one test problem (bc3b1c6). Module-scoped fixtures were set up
before the per-test cache fixture, so they hashed into the user's own cache
folder. Only the hash cache's 2-second guard kept them from writing there.

Done when, checked through the CLI on a copy of §2's example with three
commits of records:
- **First commit:** everything built.
- **Second commit:** the input changed and everything remade.
- **Third commit:** only `output1#u2` remade.

What each query gave:
- `timeline output1#u2` gives 3 versions, newest first, each with its hash,
  size, made-at commit and environment.
- `lineage output2` gives `output1#u1` and `output1#u2` at the second commit
  (not `output1#u2`'s latest), each made from `data/input1.csv` with its hash.
- `lineage output1#u2 --used-by` gives `output2`.
- `find --hash` of the first `output1#u1` hash gives that one version, and
  `find --environment` gives all 7 versions. A hash with no match exits 1.
- `get output1#u1@<first>` gives the first bytes. `get` at a commit with no
  record exits 1, saying so. An unknown address, or `find` with neither
  option, is a usage error, exit 2.
- tests/test_history.py (26 tests) also covers bytes not in git, and bytes
  that aren't the recorded ones (exit 1).

The checks at bc3b1c6: 671 passed; mypy no issues in 62 files; ruff passed;
100 files formatted. src 7,553 lines, tests 8,744.

### Phase 5: quotes against papers — done

Built:
- the `[evidence]` extra: pypdf >= 5 and rapidfuzz >= 3, locked at pypdf
  7.0.0 and rapidfuzz 3.14.6;
- evidence/papers.py: papers kept in the cache's `papers` namespace, either
  added from a file or fetched through urllib (arXiv's `<id>v<version>`, or
  else Unpaywall's best open-access PDF);
- evidence/quotes.py: EVIDENCE_PAPER_MISSING and EVIDENCE_QUOTE_NOT_FOUND,
  always warnings. A quote is sought within a `page=` location's page, or else
  in the whole text;
- `api.papers` and `api.quotes`;
- `astra paper add DOI [--version N] [--file PDF] [--email ADDRESS] | list
  [PATH] | verify [PATH]`.

Size: about 480 lines. The design gives no size; I set "near 400" in the
builder's brief.

Done when, checked through the CLI on §2's example with three evidence items
citing one DOI, and a two-page PDF made with the test's helper:
- before `add`:
  - `list` says the paper is "not in the cache" and gives the command;
  - `verify` gives three EVIDENCE_PAPER_MISSING warnings, exit 0;
- `add --file` keeps the paper, and `list` then says "in the cache";
- `verify`, exit 0:
  - finds the quote on page 2 with `page=2`, across a line break, and gives no
    warning;
  - with `page=1`, gives EVIDENCE_QUOTE_NOT_FOUND, "sought on page 1";
  - for an invented quote, gives the same warning, "sought in its whole text";
- a file that isn't a PDF, and a non-arXiv DOI without `--email`, exit 2 with a
  message saying what to give;
- `validate --json` imports neither pypdf nor rapidfuzz.

A real fetch of `10.48550/arXiv.1706.03762 --version 7` kept 15 pages. On this
machine it needed `SSL_CERT_FILE` set; without it the message is clear and the
exit is 2.

The checks at 3329109: 695 passed; mypy no issues in 67 files; ruff passed;
106 files formatted; `uv lock --check` consistent.

## Where I stopped, and why

Nowhere short. All six phases were built and each one's "Done when" holds,
checked by me. After phase 5 I committed only this report and the proposed
CLAUDE.md.

Not built, because no brief asks for them:
- the universe view's statuses "after a check" (design §4.6);
- a JSON shape for `history` and `paper`.

`astra plan` takes no `--universe` or `--output`; that narrowing is API-only.

## Open questions added to design §5

Each has its row in design §5 and a `# OPEN(<id>)` mark where the code keeps
its reading. O1–O7 were there before.

Phase 0:
- O8: the root breaks both NOT_IN_REPOSITORY and UNSUPPORTED_SPEC_VERSION, and
  Annex D cases 2 and 11 contradict each other. Reading: UNSUPPORTED_SPEC_VERSION
  alone.
- O9: a `Location`'s `file` outside a repository is the path from the
  analysis's folder.
- O10: the JSON form of `astra-validation-report/1`.
- O11: a root `astra.yaml` that is a symlink is no analysis (exit 2).

Phase 1:
- O12: an id that is both an input's and an output's names the input.
- O13: a gitlink in the working tree is a folder with its own `.git`.
- O14: the `file` of a checked-out submodule's file is measured from the root's
  top.
- O15: RESERVED_PATH compares within one tree.
- O16: when a `when` on an inactive, unset decision is determined.
- O17: where a breach inherited through a selection is reported.
- O18: an unresolved key still drives what it goes through.
- O19: DERIVED_FROM_CYCLE only on the loop.
- O20: a result read in a universe its analysis isn't built in is not planned.
- O21: an input crossing an unreachable gitlink at a commit gives
  MISSING_INPUT_FILE.
- O22: `info` and `universe` are text only.
- O23: `info` and `universe` with no stack: stderr and exit 1.
- O24: `init` inside an existing work tree makes no new repository.
- O25: `cache clear` deletes only astra's namespaces.
- O26: a MUST that only the root's pass finds in a commit's file adds no
  DECLARED_ANALYSIS_INVALID. The handover's A1 recommends otherwise.

Phase 2:
- O27: no plan or view of an invalid analysis: the report, exit 1.
- O28: the JSON form of `astra-plan/1`.
- O29: the JSON form of `astra-universe-view/1`.
- O30: an inactive decision listed by an active output renders as "" and null.
- O31: `render_command`'s paths outside the working tree are measured from the
  checkout the recipe runs in.
- O32: which name `{output}` and `{inputs.<entry>}` give for a result with two
  names.
- O33: `plan(outputs=)` on request plans as the root's own outputs are planned.

Phase 3:
- O34: a record's commit where its output doesn't exist: missing, under
  MISSING_RECORD_INPUTS.
- O35: the JSON form of `astra-check-report/1`.
- O36: `committed` means HEAD holds the record byte for byte.
- O37: a stand-in at an input's path is compared by the hash the stand-in gives.
  DVC gives none, so the result is stale.
- O38: ABSENT_RESULT is also given for a result with no valid record.
- O39: what an environment scheme answers, shown per place.
- O40: which places `uncommitted_changes` and `land` count: those of the plan's
  results, passed in.
- O41: which results `land` moves, and when main's record is "later".
- O42: `check` exits 1 on evidence alone that isn't unchanged.
- O43: `land` across file systems: copy to a temporary file, rename, remove the
  source.

Phase 4:
- O44: which history is read: `git log` from HEAD, never the working tree.
- O45: ADDR is resolved against today's plan, and renames are not followed.
- O46: a result of an analysis from a commit has one version.
- O47: `get` where the commit lacks the bytes: exit 1.
- O48: which version `lineage` gives; `--used-by` goes one level.
- O49: the API form `api.history(path) -> History`.
- O50: history is text only, and its exit codes.
- O51: `find` searches only today's planned places, with exactly one criterion.

Phase 5:
- O52: `paper list` and `verify` read only the root's evidence.
- O53: `verify` reads only the cache; `add` fetches.
- O54: a location with no `page=` means the whole text. With several, the
  first is used. A page the PDF hasn't got gives nothing, and the warning says
  how many pages it has.
- O55: Unpaywall's email comes from `--email` only, never from git or the
  environment.
- O56: when a quote is found: `exact` only, NFKC and whitespace evened out,
  partial_ratio ≥ 90. Also the two codes and where they are reported.
- O57: how papers are kept: the DOI lowercased, plus the version. Only arXiv's
  versions are fetched, and only Unpaywall's best copy.
- O58: `api.papers` and `api.quotes`; text only, no `--json`.

## What seemed wrong or unclear

Most worth your time first:

1. **CLAUDE.md** is stale. Its pin line reads b8f5597, and it describes the
   old design, its plans and decision numbers. A replacement is proposed in
   `design/2026-11-07-proposed-CLAUDE.md`.
2. **astra-spec's valid fixtures break validator rules.** Analysis-002, -004
   and -005 are single documents that are valid by schema. So
   tests/test_fixtures.py compares only parse, schema and
   UNSUPPORTED_SPEC_VERSION codes. Is that the oracle reading you intend?
3. **Annex D cases 2 and 11 contradict each other** for a root outside any
   repository with a bad `spec_version` (O8).
4. **O26** goes against the handover's recommendation A1.
5. **Design §4.6 gives the universe view statuses "after a check"**, but no
   phase's brief builds them. Phase 2's brief said to leave no slot, and phase
   3's "Builds" doesn't list them. Not built.

Design text that has drifted from the build:
- **§4.7**
  - It says records.py works out places. They are in `universes.places`,
    beside the planned results, as §6 phase 1 implied.
  - It gives `check(stack, at=…)`. `at` is on `api.check(path, at=…)`
    instead, since a stack already says where its root was read.
- **§4.8**
  - `new_record` takes a `checkout` keyword to find the files it hashes.
  - `uncommitted_changes` and `land` take the plan's results (O40).
  - A reviewer showed that a runner can easily pass `result.run_at` as
    `commit` for a driven analysis from a commit (§21 FALSE_RECORD). The
    docstrings now say which commit §19 means.
- **§4.12**
  - It gives `astra plan` no `--universe` or `--output`, so `plan(universes=,
    outputs=)` and `check(...)`'s narrowing are API-only.
  - `check` exits 1 also on evidence alone (O42).
- **§2**
  - It lists the `[evidence]` extra. It was taken out of pyproject in phase 0
    and comes back in phase 5.
  - astra-spec's `llms.txt` (`astra guide`) still describes pre-0.1 files.
- **§5's table** (only new rows were added overnight):
  - O4's *Kept in* names only `records.uncommitted_changes`, but
    `Repository.changes` carries OPEN(O4) too.
  - O30's reading now lives in `plan.selected`.
  - O32's wording lags the code.
  - O35 doesn't list the `environment` field that O39 added.

Behaviour to know about:
- **Size.** Phase 1 came in about 25% over its brief (about 3,750 lines
  against about 3,000). The other phases came in at or under.
- **YAML.**
  - A cyclic YAML alias (`a: &x [1, *x]`) is an internal error (exit 2).
    astra-spec's test_loader calls it INVALID_SYNTAX. A check for it was built
    and then removed under principle 3. Your call.
  - ruamel reads `!!bool yes` and `!!int 0b1` leniently.
- **The validity cache** is keyed by version. An editable dev install can serve
  a stale DECLARED_ANALYSIS_INVALID verdict, and the key leaves out plugin
  stand-ins.
- **Concurrent fetches** into one remote store can lose git's ref lock and read
  as REMOTE_UNREACHABLE.
- **Repeated diagnostics.** `validate` drops only identical ones, so a rule
  both passes find with different messages shows twice.
- **Warnings.** `plan`, `view` and `check` print none on a valid stack (e.g.
  RESULT_IN_TWO_PLACES); only `validate` does.
- **The run's checkout.** Nothing removes a checkout made by
  `Repository.worktree`. `astra cache clear` during a run deletes that run's
  checkout, which strains design §4.9's "everything in it is safe to delete".
- **The hash cache** ignores a file modified less than 2 s before it is hashed,
  a racy-git guard the design doesn't mention.
- **`check --at`:**
  - an analysis in a submodule counts as one from a commit, so its results that
    no recipe reads get no bytes status;
  - `--at` still needs an `astra.yaml` in the working tree.
- **History:**
  - two analyses' results can share an address, and ADDR takes the root's
    (O45);
  - each record path costs one `git log` and each version a fresh reader, so
    `find` will be slow over hundreds of results with long histories;
  - `--used-by` and lineage across repositories (a submodule's records) are
    unbounded in time (O48);
  - history has no JSON shape, so lightcone-cli can't consume it yet.
- **Intermediate commits.** Some don't pass alone: phase 1's parallel builders,
  and phase 3's 5e15d36–2b7ce7a, which predate their import-cost entries.
  Every phase's last commit passes.

- **Papers:**
  - The fetch tests stand in for the network by monkeypatching
    `urllib.request.urlopen`. Is that inside principle 6?
  - Only Unpaywall's best copy is fetched. For some publishers (Nature, in the
    builder's trial) that copy is an HTML page, and the paper then needs
    `--file`.
  - NFKC and a `ratio` fallback go beyond the brief's "whitespace evened out"
    (O56). Without them, ligatures miss the threshold, and a long invented
    quote scores near 100 against a short page.
  - `api.papers` and `api.quotes` aren't in design §2's list of public
    functions.
  - pypdf 7.0.0 came out on 2026-11-06, and `>= 5` is tested only against it.
- **Phase sizes.** Design §6 gives none for phases 4 and 5. I set "near 400"
  for each, and they came to about 540 and 480.

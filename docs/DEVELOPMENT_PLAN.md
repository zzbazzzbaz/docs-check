# Development Plan for thesis-check (Thesis Format Review)

## Project Purpose and Goals

Build an automated format checker for university graduation theses. A student uploads a `.docx`
file saved from WPS and receives a per-item, locatable and explainable list of formatting problems.
The same problems are written back into the document as Word comments so the student can find each
one without asking where it is.

Scope of this plan: **204 of the 210 rules** defined by the school. Batch 1 is 197 rules
(single-object attribute and structure checks). Batch 2 is 7 rules that need a document-wide index
or a derivation (three-line tables, formula numbering, cross-references, citation order).

The remaining 6 rules are explicitly out of scope: 5 bibliography-format rules (deferred until
batch 1 is in use) and 1 rule that requires rendered page geometry (deferred with the PDF channel).

The project must stay small. The reconciliation harness proved that a hand-written OOXML parser
(about 1300 lines) can reproduce a commercial office suite's view of formatting to 99.999 percent
over 421704 comparisons on 40 documents. The value of this project is discipline, not cleverness:
parse facts, then judge them, and keep the two apart.

## Context and Background

### Existing artefacts

| Path | What it is |
|---|---|
| `docs/` | The 210 rules, grouped by scope. **The single authoritative source for judgement.** |
| `docs/chat/9.26/` | Two design documents: the requirements document and the technical design. |
| `docs/` (school specification folder) | The school's specification text and the sample document (calibration only). |
| `test2/` | The reconciliation harness: 40 documents, eight comparison suites, WPS used as an oracle. |
| `test2/snapshots/` | 490 gzipped result snapshots (4.6 MB). **The equivalence baseline for the parser rewrite.** |
| `test2/corpus/` | 40 documents: 28 synthetic rule samples, school material, real student theses. |
| `deploy/` | Headless WPS image and compose file. Development-time calibration only. |
| `thesis-check/` | The product. Phase 0 (scaffold) is complete and its gates are green. |

### Phase 0 status (already complete)

- `pyproject.toml` with uv, src layout, runtime dependencies limited to `lxml` and `fastapi[standard]`
- `.importlinter` with two enforced contracts: one-way layering, and no `lxml` import in
  `rules`, `semantics` or `index`
- Layer packages created with their responsibilities and prohibitions documented in `__init__.py`
- `errors.py` exception hierarchy, `pipeline.review()` and `cli` as honest stubs
- `scripts/check.sh` gate; verified green: ruff, ruff format, `mypy --strict`, `lint-imports` and
  pytest. The forbidden-import contract was negatively tested and does fail when violated.

### Key decisions already taken (do not revisit)

| # | Decision |
|---|---|
| D1 | Rewrite the parser following the `test2` logic, not by editing `test2` in place. Verify against the snapshots. |
| D2 | Provenance is resolved **on demand** when a check fails; it is not stored during parsing. Value resolution and trace resolution must share one implementation. |
| D3 | Service is FastAPI with a single-page HTML upload and download form. Processing is synchronous. |
| D4 | Corpus is layered: synthetic samples and school material are versioned; real theses are not. |
| D5 | Build order: parse, semantics, rules, report, comment write-back, index. |
| D6 | Rule suppression is downgraded to selector filtering. |
| D7 | The contradictory-value advisory is not implemented. |
| D8 | Comment write-back is not abstracted into a general XML patch capability. |

### Hard constraints

- The rules layer must never touch XML. Adding an attribute rule must cost one line of data.
- Values that cannot be resolved are `None`, meaning undetermined. They are never treated as passing.
- Unrecognised block roles are reported, never silently dropped.
- No placeholder code, no TODO markers, no speculative abstractions.
- British English, ASCII-only, in all committed source comments and documentation.

## Development Tasks

### Phase 1: Packet Layer and Frozen Document Model

- [ ] Implement `src/thesischeck/parse/package.py`
  - [ ] Locate and read parts: `word/document.xml`, `word/styles.xml`, `word/numbering.xml`,
        theme parts, header and footer parts, and the relationship files
  - [ ] Implement the untrusted-input defences required by NFR-2: entity resolution off, network
        off, huge-tree mode off, entry-count and decompressed-size limits, compression-ratio limit,
        rejection of traversal entry names, rejection of encrypted archives and macro-enabled files
  - [ ] Define `BadDocument` raise points with user-readable messages for every rejection
- [ ] Implement `src/thesischeck/parse/model.py`
  - [ ] Frozen dataclasses with `slots=True`: `Para`, `Run`, `Table`, `Section`, `Box`, `Field`, `Object`, `NumPr`
  - [ ] Every node carries the lxml element reference used later for comment write-back
  - [ ] No judgement logic anywhere in this module
- [ ] Write unit tests in `tests/unit/test_package.py` and `tests/unit/test_model.py`
  - [ ] Build minimal archives in memory with `zipfile`; no fixture documents required
  - [ ] One test per defence: entity expansion, oversized archive, too many entries, traversal name, encrypted archive
  - [ ] Assert `BadDocument` is raised with a readable message, never a raw exception
- [ ] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

### Phase 2: Effective Format Resolution

- [ ] Implement `src/thesischeck/parse/effective.py`
  - [ ] Cascade order: run properties, character style, paragraph style chain including `basedOn`,
        default paragraph style, `docDefaults`, theme fonts
  - [ ] Unit normalisation: `w:sz` to points, twips to points, `firstLineChars` priority over
        `firstLine`, line rule auto to multiple, exact and atLeast flagged for rejection
  - [ ] Single resolution entry point that optionally collects a trace for provenance (D2)
  - [ ] Font slots resolved separately: `eastAsia` for Chinese, `ascii` for Western
- [ ] Write unit tests in `tests/unit/test_effective.py`
  - [ ] One test per cascade level, asserting the resolved value and, where traced, the source label
  - [ ] Regression tests for the known traps: `ABSTRACT` inheriting `ascii` from `Normal`,
        `heading 3` with contradictory first-line values, missing line spacing defaulting to single,
        negative hanging indent preserved, `numId` of zero meaning numbering explicitly cancelled
- [ ] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

### Phase 3: Document Model

- [ ] Implement `src/thesischeck/parse/document.py`
  - [ ] Block sequence of paragraphs and tables in file order, with content controls treated as
        transparent and paragraph numbering not reset when descending into them
  - [ ] Paragraph records: visible text excluding field instructions and Word control characters,
        style name, outline level, alignment, line spacing, indentation, effective numbering
  - [ ] Run records: text, effective fonts, size, bold, italic, vertical alignment
  - [ ] Handle `w:noBreakHyphen`, `m:t` and other text carriers; exclude `w:pPr/w:tabs`
  - [ ] Table records: only top-level tables counted; count paragraphs by descending through rows
        and cells; resolve per-cell borders by positional mapping (first row to top, interior rows
        to insideH, first column to left, interior columns to insideV)
  - [ ] Text box records collected on a separate path; `mc:Fallback` duplicates skipped
- [ ] Write unit tests in `tests/unit/test_document.py`
  - [ ] Assert block coverage is complete and non-overlapping for the synthetic documents
  - [ ] Assert the control-character and field-instruction exclusions
  - [ ] Assert that substituting a top-level table does not disturb paragraph numbering
- [ ] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

### Phase 4: Sections, Headers, Footers, Fields and Objects

- [ ] Implement `src/thesischeck/parse/section.py`
  - [ ] Section properties from the body-level and paragraph-level `sectPr`
  - [ ] Header and footer references per section, distinguishing a section's own reference from an
        inherited one
  - [ ] Page setup: paper size, margins, page number format, page break markers in all three forms
        (section break, explicit page break, page-break-before)
- [ ] Implement fields and objects
  - [ ] Field types and spans, with the table-of-contents span available for scope delimitation
  - [ ] Images from `w:drawing` and formulae from both `w:object` and `m:oMath`
- [ ] Write unit tests covering inheritance of headers, page break detection in all three forms,
      and formula counting without double counting `m:oMathPara`
- [ ] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

### Phase 5: Equivalence Gate

- [ ] Add a debug-only `--compat-dump` mode that emits results in the same shape as the `test2`
      snapshots
- [ ] Restore the snapshots with `test2/snapshots.sh unpack` and compare, using the self-developed
      side only
- [ ] Resolve every difference: either fix the rewrite or record the difference with an explanation
- [ ] Record the outcome, including any accepted differences, in the technical design
- [ ] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review
- [ ] Do not begin Phase 6 until this gate is zero-diff or every difference is explained and accepted

### Phase 6: Semantics (Scopes, Roles, Selectors)

- [ ] Implement `src/thesischeck/semantics/scope.py`
  - [ ] Partition the document into the eight scopes using keyword text with internal whitespace
        removed
  - [ ] Exclude table-of-contents-styled paragraphs from boundary detection, while allowing the
        table-of-contents title itself to be the boundary
- [ ] Implement `src/thesischeck/semantics/roles.py`
  - [ ] Total role assignment: every block receives a role; unrecognised blocks become `UNKNOWN`
  - [ ] Heading levels from outline level or style name only, never guessed from size or bold
- [ ] Implement `src/thesischeck/semantics/select.py`
  - [ ] Named selectors for every object used by more than one rule
  - [ ] Character-based selectors: runs containing Chinese characters, runs containing ASCII letters
        or digits, superscript runs, caption runs
  - [ ] Numbering-aware selectors implementing the downgraded suppression (D6)
- [ ] Implement `src/thesischeck/semantics/matchers.py`
  - [ ] Shared predicates: looks like a reference number, chapter text, appendix sub-heading,
        figure or table caption, formula number
  - [ ] Confirm the mutual exclusion between the two reference-numbering rules is achieved by the
        shared predicate, with no engine mechanism involved
- [ ] Write unit tests asserting the recognisers are supersets: lower-case appendix letters, Chinese
        numeral appendices, spaced and unspaced chapter headings, and Arabic-numeral chapters are
        all recognised
- [ ] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

### Phase 7: Rule Engine and Test Harness

- [ ] Confirm the outstanding judgement decisions recorded in the requirements document before
      encoding any affected rule: figure and table caption alignment, strictness of the
      every-formula-has-a-number rule, body line spacing, first-level heading alignment, reference
      heading spacing, and appendix float numbering. Record the outcome; do not guess.
- [ ] Implement `src/thesischeck/rules/base.py`
  - [ ] `Rule` dataclass holding rule identifier, selector, property extractor, expectation,
        comparison kind and source citation
  - [ ] `Issue` and `Verdict`: fail, undetermined, and pass which never reaches the report
  - [ ] Comparators: equality, approximate with tolerance, pattern, membership, count range
- [ ] Implement `src/thesischeck/rules/engine.py`
  - [ ] Iterate registered rules, resolve properties, emit issues
  - [ ] Catch per-rule failures as `RuleError` and continue with the remaining rules
- [ ] Create the full-compliant base document under `tests/fixtures/`
  - [ ] A hand-built minimal thesis that produces zero failures and zero undetermined results
  - [ ] Do not use the school sample document as the base; it documents the specification rather
        than representing a compliant thesis
- [ ] Implement the deviation helper in `tests/fixtures/synth.py`
  - [ ] Declarative changes: set a font, set a size, set alignment, set spacing, insert or remove a
        blank paragraph, rename a style, remove a heading
- [ ] Add the rule identifier cross-check test: the set of identifiers in the code equals the set in
      the rule documents, in both directions
- [ ] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

### Phase 8: Batch 1 Rules

- [ ] Add the batch 1 rule data for all 197 rules, one line per attribute rule
  - [ ] Cover: cover page, Chinese abstract, English abstract, table of contents entries,
        headings and body text, references, acknowledgements, appendix, and the document-wide rules
- [ ] Implement the small number of structural rules as code
  - [ ] Required-object existence, module order, automatic numbering prohibition, page break
        markers, header and footer applicability, caption positions with respect to figures and
        tables, numbering format and spacing, numbering continuity, reference paragraph integrity
- [ ] Add one case per rule, asserting that only the expected rule fires
- [ ] Add the anti-tautology cases: altering an appendix heading's outline level, lower-casing an
      appendix letter, removing a figure cross-reference, adding automatic numbering, and a
      paragraph that does not begin with a number
- [ ] Write structural tests: margin tolerance handling, blank-paragraph counting, keyword separator
      counting, and the five-line consistency check on the cover page
- [ ] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

### Phase 9: Index Layer and Invariants

- [ ] Implement `src/thesischeck/index/document_index.py`
  - [ ] Collect modules, chapters, floats, citations and table-of-contents entries
  - [ ] Use permissive collection and leave narrowing to the rules
  - [ ] Emit an explicit undetermined result when a fact cannot be collected
- [ ] Implement `src/thesischeck/index/checks.py`
  - [ ] Block coverage complete and non-overlapping
  - [ ] Scope ranges contiguous and covering the document
  - [ ] Boundary paragraphs match their keyword text
  - [ ] Chapters ordered and inside the body scope
  - [ ] Float numbers unique within their kind, reported as a warning rather than a failure
  - [ ] Citation numbers unique with contiguous first-appearance order
- [ ] Write tests for the invariants over the synthetic documents
- [ ] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

### Phase 10: Batch 2 Rules

- [ ] Implement three-line table checking (`TXT-49`)
  - [ ] Use the positional border mapping already implemented in Phase 3
  - [ ] Mark any table whose lines come only from table-style conditional formatting as judged by
        style, not as a firm conclusion
- [ ] Implement formula number correctness (`TXT-52`)
  - [ ] Chapter number must equal the containing first-level heading
  - [ ] Sequence numbers within a chapter must be exactly one to N
- [ ] Implement mandatory cross-references (`TXT-36`, `TXT-42`, `TXT-48`)
  - [ ] Search only ordinary body paragraphs; exclude captions, formula paragraphs, table cells and
        the table of contents
  - [ ] Prove by construction that removing a reference causes a report, so the rule is not a tautology
- [ ] Implement citation coverage and ordering (`REF-14`, `REF-15`)
  - [ ] Report items that are never cited; do not report citations with no matching item
  - [ ] Emit an explicit undetermined result when citations cannot be collected
  - [ ] Apply the agreed correction to the citation identifier anchor so the check is not a
        tautology
- [ ] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

### Phase 11: Reporting

- [ ] Implement `src/thesischeck/report/issues.py`
  - [ ] Normalised, stable ordering so snapshots diff cleanly
  - [ ] Machine-readable serialisation and a human-readable rendering
  - [ ] Strict separation of the three categories: failed, undetermined, unrecognised structure
  - [ ] Uncovered-items statement listing what this release does not check
- [ ] Implement locations
  - [ ] Machine layer: block identifier, run index, element reference
  - [ ] Human layer: scope, chapter, section, ordinal within the scope, text excerpt, and the exact
        character span for run-level problems
- [ ] Implement the pipeline in `src/thesischeck/pipeline.py` and wire `cli.py` to it
  - [ ] Produce the issue list, the human-readable report and the annotated document
- [ ] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

### Phase 12: Comment Write-Back

- [ ] Implement `src/thesischeck/report/annotate.py`
  - [ ] Insert comment range markers and the comment reference run
  - [ ] Write the comments part, register the content type and add the relationship
  - [ ] Aggregate problems by object so a paragraph with several problems carries one comment
  - [ ] Anchor paragraph-level problems to the whole paragraph, table problems to the first cell
        paragraph, and text-box problems to the host paragraph
  - [ ] Downgrade problems that cannot be annotated (headers, footers, page setup) to report entries
        and count them
  - [ ] Append to an existing comments part rather than replacing it
  - [ ] Insert markers only; never modify body text
- [ ] Implement the four closed-loop checks and run them in tests
  - [ ] Text identity before anchoring
  - [ ] Comment count equals aggregated problem count, with downgrades counted separately
  - [ ] Body text unchanged after write-back, compared character by character
  - [ ] Re-parse the annotated document and verify each comment anchors the expected object
- [ ] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

### Phase 13: Web Service

- [ ] Implement `src/thesischeck/web/app.py`
  - [ ] Synchronous endpoints defined with `def` so FastAPI runs them in a thread pool
  - [ ] Upload endpoint returning a summary and three download links
  - [ ] Download endpoints for the issue list, the report and the annotated document
  - [ ] Request size limit, random temporary file names, and expiry-based cleanup
- [ ] Implement the single-page interface in `src/thesischeck/web/static/index.html`
  - [ ] Native form upload and fetch, no build step
  - [ ] Show the three categories separately, show the uncovered-items statement, and offer the
        three downloads
  - [ ] Student-facing wording only; no XML terminology
- [ ] Write endpoint tests using the test client, covering a valid upload, an oversized upload and a
      corrupt file
- [ ] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

### Phase 14: Hardening, Regression and Acceptance

- [ ] Run the whole corpus through the pipeline and confirm the invariants hold
- [ ] Confirm the regression snapshot of the issue list over the corpus is produced and reviewed
- [ ] Verify each non-functional requirement: performance, security, robustness, maintainability,
      testability and reproducibility
- [ ] Walk the acceptance criteria in the requirements document item by item for both batches and
      record the outcome
- [ ] Resolve or record every pending confirmation item listed in the requirements document
- [ ] Confirm the rule coverage count: 197 in batch 1 and 7 in batch 2, with none missing and none
      extra
- [ ] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

## Important Considerations & Requirements

- [ ] Do not over-engineer the solution; simple solutions are preferred
- [ ] If a change means increasing complexity, weigh up options to reduce or mitigate that complexity
- [ ] Do not add placeholder or TODO code
- [ ] Do not add speculative abstractions. The following are deliberately excluded until their
      trigger appears: rule set parameters, a PDF fact provider, externalised rule data, a task
      queue, and a general XML patch capability
- [ ] The rules layer must not import `lxml`; the contract is enforced in CI
- [ ] Adding an attribute rule must cost one line of data, one fixture case and one expectation
- [ ] Values that cannot be resolved are `None` and must be reported as undetermined, never as passing
- [ ] Unrecognised block roles must appear in the report
- [ ] Tolerance values are configurable and must not be hard-coded inside rules
- [ ] No rule may hard-code a paragraph index, a document file name, or branch on a file name
- [ ] The rule identifier set in the code must equal the set in the rule documents, verified in both
      directions
- [ ] Comment write-back must insert markers only; body text must remain character-for-character
      identical
- [ ] British English and ASCII only in committed source and documentation

## Technical Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Layering | Five layers, one-way dependencies, enforced by import-linter | The promise that a rule costs one line only holds if the rules layer never sees XML |
| Parser source | Rewrite following the harness logic, verified by equivalence dump | The harness proved the logic; rewriting gives a typed model, and the snapshots make the rewrite verifiable rather than speculative |
| Provenance | Resolved on demand, sharing one implementation with value resolution | Provenance is only needed to explain failures; two implementations would diverge |
| Model mutability | Frozen dataclasses with slots | Read-only facts, cheap, type-checked |
| Rule data location | In code, not in external configuration | Type checking, reuse of constants, no extra parsing layer |
| HTTP layer | FastAPI synchronous endpoints with `def` | Parsing is synchronous CPU work; `async def` calling it would block the event loop |
| Document mutation | In-memory tree produced by the parser, reused for write-back | Re-parsing for annotation risks anchoring to a different tree |
| Suppression | Selector filtering rather than an engine mechanism | The effect is required, the mechanism is not |
| Caching | None | A document is parsed once per review; measured cost is well under the budget |

## Testing Strategy

Tests must be fast, run without external dependencies, and run in isolation.

| Level | What it covers | Data |
|---|---|---|
| Unit | Cascade resolution, normalisation, selectors, matchers, comparators, packet defences | Minimal XML fragments and in-memory archives built in the test |
| Rule cases | Each rule fires on a deviation and stays silent otherwise | Full-compliant base document plus a declarative change |
| Invariants | Index and role consistency | Synthetic documents |
| Equivalence | Parser output against the harness snapshots | Restored snapshots, self-developed side only |
| Annotation | The four closed-loop checks | Synthetic documents, including a deliberately unanchorable problem |
| Snapshot | Whole-pipeline issue list | Synthetic documents in CI; real corpus locally via the corpus environment variable |

Rules:

- Behavioural tests are written before the code where practical
- Each rule has at least one hit case and one pass case
- Each hit case asserts that only the expected rule fires
- Anti-tautology cases are mandatory for every existence or cross-reference rule
- The regression snapshot is committed in a stable order so differences are meaningful
- Real-corpus tests skip automatically when the corpus environment variable is unset

## Debugging Protocol

If issues arise during implementation:

- **Tests fail**: analyse the failure reason and fix the root cause; do not work around it
- **Equivalence differs**: compare against the reference snapshot field by field, and decide whether
  the difference is a rewrite defect or an accepted improvement; record the decision
- **A rule fires when it should not**: check the selector first, then the comparator, then the
  expectation; check whether the recogniser is a superset as required
- **Performance issues**: profile before changing anything; the parser is well within budget, so a
  regression usually means repeated work, not an algorithmic problem
- **Integration issues**: check the layering contract output first; a broken contract explains most
  unexpected import failures
- **Unclear requirements**: stop and seek clarification rather than guessing

## QA Checklist

- [ ] All user instructions followed
- [ ] All requirements implemented and tested
- [ ] No critical code smell warnings
- [ ] British or Australian spelling used throughout
- [ ] No smart formatting, non-ASCII characters or emojis
- [ ] Code follows project conventions and standards
- [ ] Documentation is updated and accurate if needed
- [ ] Security considerations addressed
- [ ] Integration points verified
- [ ] `./scripts/check.sh` passes: ruff lint, ruff format check, `mypy --strict`, import-linter, pytest
- [ ] Layering contracts kept, including the prohibition on `lxml` in rules, semantics and index
- [ ] Rule identifier cross-check passes in both directions
- [ ] Every rule has a hit case and a pass case
- [ ] Anti-tautology cases present for existence and cross-reference rules
- [ ] Equivalence dump against the harness snapshots reviewed, with differences explained
- [ ] Undetermined and unrecognised-structure results appear in the report and are not treated as passing
- [ ] Uncovered-items statement present in every report
- [ ] Comment write-back leaves body text character-for-character identical
- [ ] Coverage confirmed at 197 batch 1 rules and 7 batch 2 rules

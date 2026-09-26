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

- [x] Implement `src/thesischeck/parse/package.py`
  - [x] Locate and read parts: `word/document.xml`, `word/styles.xml`, `word/numbering.xml`,
        theme parts, comment part, and the relationship files
  - [x] Implement the untrusted-input defences required by NFR-2: entity resolution off, network
        off, huge-tree mode off, entry-count and decompressed-size limits, compression-ratio limit,
        rejection of traversal entry names, rejection of encrypted archives and macro-enabled files
  - [x] Define `BadDocument` raise points with user-readable messages for every rejection
- [x] Implement `src/thesischeck/parse/model.py`
  - [x] Frozen dataclasses with `slots=True`: `Para`, `Run`, `Objects`, `NumPr`, plus the `Story`
        and `LineRule` enums
  - [x] Every node carries the lxml element reference used later for comment write-back
  - [x] No judgement logic anywhere in this module
- [x] Write unit tests in `tests/unit/test_package.py` and `tests/unit/test_model.py`
  - [x] Build minimal archives in memory with `zipfile`; no fixture documents required
  - [x] One test per defence: entity expansion, oversized archive, too many entries, traversal name,
        encrypted archive, compression bomb, oversized part, oversized total
  - [x] Assert `BadDocument` is raised with a readable message, never a raw exception
- [x] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

Two adjustments made while implementing this phase:

1. `Table`, `Section`, `Box`, `Field` and `Object` are **deferred to the phases that produce them**
   (3 and 4). Defining their fields now would be guesswork, and guessing field names is how a model
   ends up being rewritten twice. Phase 1 defines the paragraph-level facts, which is what the
   majority of rules read.
2. Relationship parsing was added here rather than in Phase 4, because locating header and footer
   parts is a packet-layer concern. External relationship targets are skipped so that no URL from an
   uploaded document is ever followed.

Finding worth recording: libxml2 already enforces a maximum entity amplification factor, so a
billion-laughs document is **rejected outright** rather than merely left unexpanded. The test asserts
the readable rejection and the fact that it returns immediately.

### Phase 2: Effective Format Resolution

- [x] Implement `src/thesischeck/parse/effective.py`
  - [x] Cascade order: run properties, character style, paragraph style chain including `basedOn`,
        default paragraph style, `docDefaults`, theme fonts
  - [x] Unit normalisation: `w:sz` to points, twips to points, `firstLineChars` priority over
        `firstLine`, line rule auto to multiple, exact and atLeast flagged for rejection
  - [x] Single resolution entry point that optionally collects a trace for provenance (D2)
  - [x] Font slots resolved separately: `eastAsia` for Chinese, `ascii` for Western
- [x] Write unit tests in `tests/unit/test_effective.py`
  - [x] One test per cascade level, asserting the resolved value and, where traced, the source label
  - [x] Regression tests for the known traps: `ABSTRACT` inheriting `ascii` from `Normal`,
        `heading 3` with contradictory first-line values, missing line spacing defaulting to single,
        negative hanging indent preserved, `numId` of zero meaning numbering explicitly cancelled
- [x] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

### Phase 3: Document Model

- [x] Implement `src/thesischeck/parse/document.py`
  - [x] Block sequence of paragraphs and tables in file order, with content controls treated as
        transparent and paragraph numbering not reset when descending into them
  - [x] Paragraph records: visible text excluding field instructions and Word control characters,
        style name, outline level, alignment, line spacing, indentation, effective numbering
  - [x] Run records: text, effective fonts, size, bold, italic, vertical alignment
  - [x] Handle `w:noBreakHyphen`, `m:t` and other text carriers; exclude `w:pPr/w:tabs`
  - [x] Table records: only top-level tables counted; count paragraphs by descending through rows
        and cells; resolve per-cell borders by positional mapping (first row to top, interior rows
        to insideH, first column to left, interior columns to insideV)
  - [x] Text box records collected on a separate path; `mc:Fallback` duplicates skipped
- [x] Write unit tests in `tests/unit/test_document.py`
  - [x] Assert block coverage is complete and non-overlapping for the synthetic documents
  - [x] Assert the control-character and field-instruction exclusions
  - [x] Assert that substituting a top-level table does not disturb paragraph numbering
- [x] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

### Phase 4: Sections, Headers, Footers, Fields and Objects

- [x] Implement `src/thesischeck/parse/section.py`
  - [x] Section properties from the body-level and paragraph-level `sectPr`
  - [x] Header and footer references per section, distinguishing a section's own reference from an
        inherited one
  - [x] Page setup: paper size, margins, page number format, page break markers in all three forms
        (section break, explicit page break, page-break-before)
- [x] Implement fields and objects
  - [x] Field types and spans, with the table-of-contents span available for scope delimitation
  - [x] Images from `w:drawing` and formulae from both `w:object` and `m:oMath`
- [x] Write unit tests covering inheritance of headers, page break detection in all three forms,
      and formula counting without double counting `m:oMathPara`
- [x] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

### Phase 5: Equivalence Gate

- [x] Add a debug-only `--compat-dump` mode that emits results in the same shape as the `test2`
      snapshots
- [x] Restore the snapshots with `test2/snapshots.sh unpack` and compare, using the self-developed
      side only
- [x] Resolve every difference: either fix the rewrite or record the difference with an explanation
- [x] Record the outcome, including any accepted differences, in the technical design
- [x] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review
- [x] Do not begin Phase 6 until this gate is zero-diff or every difference is explained and accepted

Outcome (self-developed side only; comparison reads the `.gz` snapshots directly, so `unpack` was
not needed):

- `src/thesischeck/parse/compat.py` renders the four suites from the parsed `Document`. Raw
  indentation twips, explicit attributes, formula numbers and WPS synthetic fields are taken back
  from the lxml references retained on each node, so the typed model stays product-focused.
- `tests/golden/test_equivalence.py` holds the pure `diff_records` comparator plus a per-document
  gate over `test2/corpus` x four suites; it skips when the corpus or snapshots are absent.
- Local run over 40 documents: `own` 15811 paragraphs / 45950 runs / 2793 fields, `ownpages`
  409 sections / 2454 header-footer records / 983 header-footer paragraphs, `ownborders` 228
  tables / 1180 sampled cells, `owntextbox` 16 boxes. **Every field is identical; the
  accepted-difference list is empty.**

### Phase 6: Semantics (Scopes, Roles, Selectors)

- [x] Implement `src/thesischeck/semantics/scope.py`
  - [x] Partition the document into the eight scopes using keyword text with internal whitespace
        removed
  - [x] Exclude table-of-contents-styled paragraphs from boundary detection, while allowing the
        table-of-contents title itself to be the boundary
- [x] Implement `src/thesischeck/semantics/roles.py`
  - [x] Total role assignment: every block receives a role; unrecognised blocks become `UNKNOWN`
  - [x] Heading levels from outline level or style name only, never guessed from size or bold
- [x] Implement `src/thesischeck/semantics/select.py`
  - [x] Named selectors for every object used by more than one rule
  - [x] Character-based selectors: runs containing Chinese characters, runs containing ASCII letters
        or digits, superscript runs, caption runs
  - [x] Numbering-aware selectors implementing the downgraded suppression (D6)
- [x] Implement `src/thesischeck/semantics/matchers.py`
  - [x] Shared predicates: looks like a reference number, chapter text, appendix sub-heading,
        figure or table caption, formula number
  - [x] Confirm the mutual exclusion between the two reference-numbering rules is achieved by the
        shared predicate, with no engine mechanism involved
- [x] Write unit tests asserting the recognisers are supersets: lower-case appendix letters, Chinese
        numeral appendices, spaced and unspaced chapter headings, and Arabic-numeral chapters are
        all recognised
- [x] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

Outcome:

- `thesischeck.semantics` now wraps the frozen `Para` in `Block(para, scope, role)`; `Scope` and
  `Role` are defined in `scope.py` / `roles.py` and re-exported from `blocks.py` to avoid a cycle.
  Real-corpus run (40 documents, 15411 paragraphs): every document has contiguous, non-overlapping
  scope ranges covering the whole file, and every paragraph receives a role. Total unrecognised
  share is 3.39 per cent, concentrated in one document whose chapter headings omit the `第X章`
  prefix; its body therefore falls into the table-of-contents scope and is reported as `UNKNOWN`
  (the missing chapter marker is `TXT-51` / `GLB-26` territory). All other 39 documents have zero
  unrecognised blocks.
- `.importlinter` contract 2 gained `allow_indirect_imports = true`: the layering requires
  semantics (and later rules / index) to consume `parse.model`, which itself imports `lxml` as the
  leaf dependency. The contract still forbids a direct `lxml` import in these layers (negatively
  tested).

### Phase 7: Rule Engine and Test Harness

- [x] Confirm the outstanding judgement decisions recorded in the requirements document before
      encoding any affected rule: figure and table caption alignment, strictness of the
      every-formula-has-a-number rule, body line spacing, first-level heading alignment, reference
      heading spacing, and appendix float numbering. Record the outcome; do not guess.
- [x] Implement `src/thesischeck/rules/base.py`
  - [x] `Rule` dataclass holding rule identifier, selector, property extractor, expectation,
        comparison kind and source citation
  - [x] `Issue` and `Verdict`: fail, undetermined, and pass which never reaches the report
  - [x] Comparators: equality, approximate with tolerance, pattern, membership, count range
- [x] Implement `src/thesischeck/rules/engine.py`
  - [x] Iterate registered rules, resolve properties, emit issues
  - [x] Catch per-rule failures as `RuleError` and continue with the remaining rules
- [x] Create the full-compliant base document under `tests/fixtures/`
  - [x] A hand-built minimal thesis that produces zero failures and zero undetermined results
  - [x] Do not use the school sample document as the base; it documents the specification rather
        than representing a compliant thesis
- [x] Implement the deviation helper in `tests/fixtures/synth.py`
  - [x] Declarative changes: set a font, set a size, set alignment, set spacing, insert or remove a
        blank paragraph, rename a style, remove a heading
- [x] Add the rule identifier cross-check test: the set of identifiers in the code equals the set in
      the rule documents, in both directions
- [x] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

Outcome:

- The six pending judgement items are **not decided by the school yet**. They are implemented
  **verbatim from `docs/规则/*.md`** and recorded here unchanged for the user to forward; no
  calibration was invented. In order: (1) `TXT-39`/`TXT-45` captions must be centred while the
  sample is justified; (2) `TXT-32` every formula must carry a number while the sample has two
  formulas and one number; (3) `TXT-29` body line spacing of 1.5 is taken from the sample, not the
  specification text; (4) `TXT-04` first-level heading centred is taken from the sample; (5)
  `REF-01` no space in the reference heading, specification and sample disagree; (6) appendix
  figure/table/formula numbers (`图A1` `表B2` `式(B3)`) have no rule covering them. The two
  already-fixed items are honoured: citation-run anchoring is text-based (`[数字]`, Phase 6
  `citation_runs`) and `TXT-30` judges superscript (`superscript_runs`).
- `rules/base.py`: `Rule[Obj, Val]` is a frozen data record (`id`, `of`, `prop`, `expect`, `src`,
  `cmp`, `tol`); `Verdict` is `PASS`/`FAIL`/`UNDETERMINED`; `Issue` carries rule, verdict, where,
  got, expect, src and an optional `RuleError`. Comparators are exactly the five required; tolerance
  values live in `Tolerances` and rules reference a `ToleranceKey`, never a number.
- `rules/engine.py`: `run_rules(blocks, registry, *, tolerances)` iterates the registry, treats
  `None` as `UNDETERMINED`, and converts a per-rule exception into an `UNDETERMINED` issue holding
  the `RuleError` so the remaining rules still run.
- `tests/fixtures/base.py` generates the base in memory (no committed binary): eight modules, all
  heading levels, body paragraphs, figure/table captions, a drawing, a three-line table, a formula
  paragraph with its number, reference items, appendix sub-headings, both keyword lines, header,
  footer with a PAGE field, three sections with inherited header and own footer, page setup and a
  cross-paragraph `TOC` field with `toc 1/2/3` entries.
- `tests/fixtures/synth.py` applies deviations to the base XML and repacks the archive; targets are
  readable anchor names; changes offered are font (`ea`/`west`), size, bold, alignment, line
  spacing, insert/delete a paragraph (including blank) and rename a style.
- `tests/rules/case.py` provides `CASE(rule_id, base, change, expect_only)`, asserting that the set
  of reported rules equals `expect_only` exactly. The demonstration rule `ABS-C-02` has one hit case
  and one pass case. `tests/rules/test_rule_ids.py` extracts the identifiers from the rule documents
  and checks both directions: the registered set must be a subset of the documents (hard), and the
  reverse direction skips until `ALL_IN_SCOPE_RULES_REGISTERED` is set in Phase 8.
- The base currently satisfies the single registered rule; reaching genuinely zero problems is
  deferred to Phase 8 once the rules exist, as expected.

### Phase 8: Batch 1 Rules

- [x] Add the batch 1 rule data for all 197 rules, one line per attribute rule
  - [x] Cover: cover page, Chinese abstract, English abstract, table of contents entries,
        headings and body text, references, acknowledgements, appendix, and the document-wide rules
- [x] Implement the small number of structural rules as code
  - [x] Required-object existence, module order, automatic numbering prohibition, page break
        markers, header and footer applicability, caption positions with respect to figures and
        tables, numbering format and spacing, numbering continuity, reference paragraph integrity
- [x] Add one case per rule, asserting that only the expected rule fires
- [x] Add the anti-tautology cases: altering an appendix heading's outline level, lower-casing an
      appendix letter, removing a figure cross-reference, adding automatic numbering, and a
      paragraph that does not begin with a number
- [x] Write structural tests: margin tolerance handling, blank-paragraph counting, keyword separator
      counting, and the five-line consistency check on the cover page
- [x] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

Outcome:

- **197 rules** are registered for batch 1 (cover 16, Chinese abstract 24, English abstract 23,
  table of contents 15, body 46, references 15, acknowledgements 12, appendix 18, document-wide 28).
  They were delivered in three rounds: round 1 cover + abstracts (63), round 2 table of contents +
  body (61), round 3 references + acknowledgements + appendix + document-wide (73).
- **The fully-compliant fixture reports zero problems across all 197 rules**
  (`issues_for(BASE) == []`). Reaching this needed fixture work: a blank line after the reference /
  acknowledgement / appendix titles, the acknowledgement body now carries ASCII so the Western-font
  rule has an object, the appendix sub-headings carry 1.5 line spacing, the header is 黑体 五号,
  the footer PAGE field runs are 五号, and the page margins are 2.6 cm; the document is split into
  eight per-module sections so header/footer applicability can be tested in isolation.
- The **rule-identifier cross-check is now bidirectional and hard**: `ALL_IN_SCOPE_RULES_REGISTERED`
  is `True`, and the registered set equals the document set minus the six items not built this
  release (`TXT-50`, `REF-16`–`REF-20`) and the seven deferred to batch 2 (`TXT-36`, `TXT-42`,
  `TXT-48`, `TXT-49`, `TXT-52`, `REF-14`, `REF-15`). The difference is empty.
- **Automatic-numbering "step aside"** is a selector filter, not an engine mechanism: the shared
  selectors `ref_items_no_auto` / `appendix_subs_no_auto` / `h4_no_auto` drop paragraphs whose
  effective `numPr` is set, so `REF-10`/`REF-11`/`APP-06`/`TXT-19` never see them; `GLB-28` reports
  them once. `REF-10` and `REF-21` share `matchers.looks_like_number`, so a paragraph that does not
  begin with a number is reported by `REF-21` only.
- Document-wide facts reach the rules through a read-only `CheckContext` (the block sequence plus
  sections, all paragraphs including text boxes, and whether `numbering.xml` exists); it is a tuple
  subclass, so every existing block selector keeps working unchanged. Page-number runs are extracted
  in the parser (`HeaderFooter.page_number_runs`), keeping the rules layer free of XML.
- **Known couplings / literal readings recorded**: `GLB-22`'s case also trips `GLB-14` because
  removing the table-of-contents-to-body section break merges the two sections (so the contents also
  gains a page number); `GLB-27`'s verdict is tested directly because reordering modules changes the
  scope partition itself; `GLB-28`'s report-end summary count belongs to the Phase 11 report layer;
  `REF-11` counts continuity over numbered items only so an unnumbered item is reported by `REF-21`
  alone; a section-break paragraph is treated as a structural marker, not a blank line, by the
  "exactly one blank line after a title" rules.

### Phase 9: Index Layer and Invariants

- [x] Implement `src/thesischeck/index/document_index.py`
  - [x] Collect modules, chapters, floats, citations and table-of-contents entries
  - [x] Use permissive collection and leave narrowing to the rules
  - [x] Emit an explicit undetermined result when a fact cannot be collected
- [x] Implement `src/thesischeck/index/checks.py`
  - [x] Block coverage complete and non-overlapping
  - [x] Scope ranges contiguous and covering the document
  - [x] Boundary paragraphs match their keyword text
  - [x] Chapters ordered and inside the body scope
  - [x] Float numbers unique within their kind, reported as a warning rather than a failure
  - [x] Citation numbers unique with contiguous first-appearance order
- [x] Write tests for the invariants over the synthetic documents
- [x] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

Outcome:

- `index/document_index.py` collects the five facts and imports no XML. `DocumentIndex` holds
  `modules` (`ModuleSpan(name, start, end, title_found)`), `chapters`
  (`Chapter(no, text, start, end, outline, style, is_heading1)`), `floats`
  (`Floats(figures, tables, formulas, formula_objects)`), `citations`
  (`tuple[Citation, ...] | None`) and `toc_entries` (`TocEntry(level, text, para)`).
  `build_index(doc, blocks)` is the entry point; `module_spans` / `detected_modules` are the
  single source of module facts.
- Permissive collection is enforced where it matters: chapter candidates are every paragraph in
  the body scope whose key text starts with `第X章`, with outline, style and `is_heading1`
  carried alongside and narrowing left to the rules; table-of-contents entries accept any
  `toc N` level so the level invariant is not a tautology. Citations are `None` (undetermined)
  when the body scope cannot be located, never an empty set.
- `index/checks.py` (`check_index(doc, index)`) runs the seven invariants, separating failures
  from warnings: float-number duplicates and undetermined citations are warnings, the rest are
  failures. Its teeth are tested by breaking a good index and asserting each check fires.
- `GLB-26` / `GLB-27` no longer own a copy of the module keywords: `document_wide` consumes
  `index.module_spans` / `detected_modules`, so the index is the only place that detects modules.
  The `GLB-27` verdict test still asserts the recognition/verdict split.
- `ownindex` joined the Phase 5 equivalence gate: `compat.dump_index` renders the reference shape
  and `tests/golden/test_equivalence.py` compares it field by field over all 40 documents.
  **Zero differences; the accepted-difference list stays empty.** The compat renderer follows the
  reference algorithm (loose citation bracket, `toc 1/2/3`); the product index is deliberately
  stricter, which is why its evidence is the invariant run rather than the snapshot.
- Real corpus (40 documents): all seven invariants pass with no failures; four warnings, all of
  the accepted kind - two documents have duplicate figure/table numbers (left to `TXT-38` /
  `TXT-44` to narrow) and one document has no body scope, so its citations are reported
  undetermined. The base document still reports zero problems across all 197 batch 1 rules
  (`issues_for(BASE) == []`).

### Phase 10: Batch 2 Rules

- [x] Implement three-line table checking (`TXT-49`)
  - [x] Use the positional border mapping already implemented in Phase 3
  - [x] Mark any table whose lines come only from table-style conditional formatting as judged by
        style, not as a firm conclusion
- [x] Implement formula number correctness (`TXT-52`)
  - [x] Chapter number must equal the containing first-level heading
  - [x] Sequence numbers within a chapter must be exactly one to N
- [x] Implement mandatory cross-references (`TXT-36`, `TXT-42`, `TXT-48`)
  - [x] Search only ordinary body paragraphs; exclude captions, formula paragraphs, table cells and
        the table of contents
  - [x] Prove by construction that removing a reference causes a report, so the rule is not a tautology
- [x] Implement citation coverage and ordering (`REF-14`, `REF-15`)
  - [x] Report items that are never cited; do not report citations with no matching item
  - [x] Emit an explicit undetermined result when citations cannot be collected
  - [x] Apply the agreed correction to the citation identifier anchor so the check is not a
        tautology
- [x] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

Outcome:

- **7 rules registered; the suite is now 204 rules** (`issues_for(BASE) == []`, base stays fully
  compliant). `TXT-36` / `TXT-42` / `TXT-48` and `REF-14` / `REF-15` live in the scope modules
  (`rules/text.py`, `rules/references.py`); the shared index access is `rules/support.context_index`.
- **TXT-49** judges the positional per-cell borders already parsed in Phase 3. `parse/model.Table`
  gained the **fact** `style_conditional_borders` (the style chain writes borders under
  `w:tblStylePr`), computed in `parse/effective.StyleDef`. When a table is non-compliant but that
  fact is true the verdict is `None` (undetermined), never a firm "not compliant". The pure function
  `three_line_verdict` is unit-tested (vertical line, missing header line, conditional-format
  downgrade, single-row table).
- **TXT-52** consumes `index.chapters` + `index.floats`; the chapter number comes from the containing
  `第X章` heading and each chapter's sequence numbers must be exactly `1…N`. Counterexamples cover
  chapter mismatch, a sequence jump and a duplicate.
- **The citation anchor was corrected** per FR-8.4: `index._citations` now collects runs by text
  (`matchers.is_citation`) instead of superscript, so `REF-14` / `REF-15` are not tautologies;
  `TXT-30` still judges superscript. `index.citations is None` yields an explicit undetermined result.
  Constructed cases prove it: deleting the `[2]` body citation reports `REF-14` only; inserting an
  early `[2]` makes first-appearance order `2, 1` and reports the first inversion by `REF-15`.
- **Anti-tautology references are proven by construction**: deleting `式(1-1)` / `图1-1` / `表1-1`
  from the ordinary body paragraph reports `TXT-36` / `TXT-42` / `TXT-48` exactly (the caption text is
  excluded from the search, otherwise `图1-1` would always be found in its own caption).
- **Base document additions**: the chapter-1 body now carries a separate reference paragraph with the
  literature citation `[1]`, the formula reference `式(1-1)` and the figure / table references
  `图1-1` / `表1-1`. `_reference_line` is placed before the table so the first-appearance order is
  `1, 2` and `REF-15` passes.
- **Recorded couplings**: renumbering a reference item (`REF-11` case) or inserting an uncited item
  (`GLB-24` case) now also trips `REF-14`, because the added entry is never cited; both cases list
  `REF-14` alongside the original rule.
- **Two documented index-level changes**: `index.index_from(paragraphs, blocks)` exposes the
  collection entry point the rules layer can call (it has no `Document`), and `CheckContext` now
  carries `doc.tables` so `TXT-49` can see top-level tables.
- `./scripts/check.sh` green: 635 tests pass, `mypy --strict`, ruff and the two layering contracts
  all pass. The rule-identifier cross-check is a hard assertion down to the six out-of-scope rules.

### Phase 11: Reporting

- [x] Implement `src/thesischeck/report/issues.py`
  - [x] Normalised, stable ordering so snapshots diff cleanly
  - [x] Machine-readable serialisation and a human-readable rendering
  - [x] Strict separation of the three categories: failed, undetermined, unrecognised structure
  - [x] Uncovered-items statement listing what this release does not check
- [x] Implement locations
  - [x] Machine layer: block identifier, run index, element reference
  - [x] Human layer: scope, chapter, section, ordinal within the scope, text excerpt, and the exact
        character span for run-level problems
- [x] Implement the pipeline in `src/thesischeck/pipeline.py` and wire `cli.py` to it
  - [x] Produce the issue list, the human-readable report and the annotated document
- [x] Perform a self-review of your code, once you are certain it is 100 percent complete to the
      requirements in this phase mark the task as done.
- [ ] STOP and wait for human review

Outcome:

- `report/issues.py` turns `list[Issue]` into a `Report` with four partitions - fail / undetermined /
  not-run (`RuleError`) / unrecognised structure - plus the uncovered-items statement. `to_json()`
  emits a stable `issues.json` (scope, block, run, rule, excerpt ordering; no timestamp, no absolute
  path, no timing) and `to_html()` a single-file `report.html` with inline CSS and no build step.
  Unrecognised structure comes from `Role.UNKNOWN` blocks; the four partition lists are separate so
  undetermined, not-run and unrecognised can never be read as passing.
- Location is two-layered (FR-9.1): machine layer is `block_id` (paragraph id) + `run_index` +
  a stable relative element path (`document/body[1]/p[38]/r[1]`); human layer is
  `module > chapter > section` with the ordinal inside the section, the paragraph excerpt and, for
  run-level problems, the exact run text. Chapter and section text are read back from the real
  paragraphs (not the whitespace-stripped anchors), so the report shows `正文 > 第一章  绪论 >
  1.1.1 现状分析（该节第 3 段）` and a "search for this" hint.
- On-demand provenance (technical design 4.2) is wired: on a FAIL the report re-walks the cascade for
  that one property through `parse.effective.run_source`, which reuses `Resolver.run` with a trace -
  no second value/source implementation. The recorded defect was fixed: the paragraph-direct layer
  no longer reuses the `run` label; both direct layers now emit the neutral `直接设置`, and the
  report composes "on the run" / "in the paragraph" by object type, or "from style X" for inherited
  values.
- The two Phase 8 leftovers are handled: the line-spacing sentinel (`NOT_MULTIPLE`, `nan`) is
  special-cased so the report says "fixed line spacing 20pt" instead of `nan`, and `GLB-28`'s
  summary count ("N paragraphs use automatic numbering") is emitted in `summary.auto_numbering_paragraphs`
  and printed in the report footer.
- `pipeline.review(docx, outdir)` runs parse -> semantics -> index -> rules -> report and writes
  `issues.json` + `report.html`; `cli.py` calls it and keeps `--compat-dump` and `--version`. The
  normative version strings sit in the report header. The annotated document remains Phase 12, so the
  pipeline writes two products today.
- Gates green: `./scripts/check.sh` passes (649 tests). The 204-rule base still reports zero problems
  end to end; a font deviation reports the expected rule with value, expectation, basis, location and
  provenance.

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

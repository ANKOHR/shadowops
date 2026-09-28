# ShadowOps

ShadowOps discovers repeated business process sequences from heterogeneous activity records. It builds a frequency-weighted process graph, estimates repetitive effort with a documented model, ranks automation candidates with risk notes, and writes an implementation spec for a selected candidate.

## Quickstart

Requires Python 3.10 or newer. The package has no runtime dependencies and uses CPU-only Python code.

```powershell
python -m shadowops fixtures --out .\demo-data
python -m shadowops discover --in .\demo-data --out .\graph.json
python -m shadowops score --in .\demo-data --ground-truth .\demo-data\ground_truth.json
python -m shadowops candidates --in .\demo-data
python -m shadowops spec top --in .\demo-data
```

The `shadowops` command is also available after installing the project with `python -m pip install -e .`. All commands emit JSON. Discovery writes the graph and inferred processes, `candidates` prints the ranked list, and `spec top` builds the top-ranked candidate spec. Malformed records are logged to stderr and included in the discovery warning list.

## Honesty boundary

All fixture activity is synthetic, generated, fictional data. Every activity record carries the `SYNTHETIC GENERATED ACTIVITY` label. The fixture generator uses no random values. Its documented seed is `20260928`, retained as provenance so future generator changes have an explicit seed value. No real company data is used.

Hours-wasted figures are model-based estimates, not measured time or measured savings from real companies. They describe the generated sample only. The CLI, generated report data, and this README label that limitation plainly. The ground-truth score measures reconstruction against the known synthetic fixture workflows, not real-world validity. The demo target is precision and recall of at least `0.80`; the generated fixture currently has exact sequence matches.

## Architecture

```text
Generated JSONL and CSV activity
              |
              v
       Format parsers
              |
              v
 Canonical event stream
              |
              v
 Group by case, sort by timestamp, mine repeated exact sequences
              |
              v
 Process graph + model estimates + risk dimensions
              |
              +----> Ground-truth precision and recall
              +----> Ranked automation candidates
              +----> Implementation spec
```

Each event includes an actor, action, object, timestamp, channel, source, case identifier, sensitivity, and synthetic-data label. Email thread, calendar, file-operation, and CSV formats have separate parsers that map source-specific fields into this event schema. A malformed row is logged and skipped. The case identifier groups events for sequence reconstruction. A process is inferred when the exact ordered action sequence appears in at least two distinct cases. The separate ground-truth file is used only for scoring, never for discovery or ranking.

The graph's node `frequency_count` is the number of observed events for that action in inferred processes. An edge's `frequency_count` is the number of times the transition occurs across cases. `case_frequency` counts distinct cases containing that transition. Process frequency is the count of cases with the exact sequence.

## Estimation model

For a process with action steps, the model uses a fixed assumed duration per event. The current per-step table is in `shadowops/model.py`; an unlisted step defaults to 5 minutes. The model assumes 70 percent of this repeated work is addressable by automation.

```text
estimated hours wasted = sum(event count * assumed minutes per event) * 0.70 / 60
estimated labor value = estimated hours wasted * GBP 32.50 wage proxy per hour
candidate value score = estimated hours wasted * wage proxy * 0.80 automation-rate assumption
```

These assumptions are intentionally visible in every process estimate and candidate evidence. They are rough model inputs for the synthetic demo, not observations about a real workforce. Counts, per-step durations, waste share, wage proxy, and calculation formula are emitted as evidence so a reviewer can recompute every number. Candidate value is a ranking heuristic, not a business case.

Risk is calculated independently from candidate value. Sensitivity ranks low, medium, and high as 1, 2, and 3. Blast radius ranks low, medium, and high as 1, 2, and 3. Reversibility ranks easy, moderate, and hard as 1, 2, and 3. The total is `2 * sensitivity + blast radius + reversibility`; totals below 6 are low, 6 through 9 are medium, and 10 or above are high. The candidate includes the score, dimensions, and reasons. The rules are a transparent demo rubric, not a security assessment.

## Determinism

Fixture records use fixed actors, dates, ordering, and case IDs. The generator has no random-number calls, so repeated generation produces byte-identical data files. Discovery, graph JSON, scoring, and candidate ordering sort their inputs and outputs to keep the same corpus byte-identical across runs. The seed value `20260928` is documented even though the current generator does not need random sampling.


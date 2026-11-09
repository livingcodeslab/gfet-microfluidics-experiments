# project-packaging — tasks and todos

**Off the priority list** — pick this up whenever there is a moment. Nothing
here blocks the ot2 features.

## Goal

Make `gdnasynth` distributable: an installable package with a **single source of
truth for dependencies**, kept in sync with `guix.scm`. The `requirements*.txt`
files were deleted on 2026-11-09; `pyproject.toml` replaces them.

## Background

- `guix.scm` — a symlink to `.guix/gdnasynth.scm` — builds with
  `pyproject-build-system`, but there was no `pyproject.toml` (nor `setup.py`)
  for it to consume until 2026-11-09.
- Its dependency lists are the de facto source of truth:

  | kind | guix packages |
  | --- | --- |
  | `propagated-inputs` (runtime) | `python-requests`, `python-pyserial`, `python-py-gnuplot`, `python-keithley2600`, `python-pyvisa` |
  | `native-inputs` (dev/build) | `python-hatchling`, `python-mypy`, `python-pylint`, `python-pytest`, `python-typing-extensions` |

## Done

- **`pyproject.toml`** (2026-11-09): PEP 621 metadata, `MIT` licence (the
  `LICENSE` file is already MIT) with `license-files = ["LICENSE"]`,
  `requires-python = ">=3.10"`, the runtime dependencies, a `dev` extra matching
  `native-inputs`, and the hatchling build backend.
- **`pyvisa` declared explicitly** — `gdnasynth/keithley.py` imports it directly;
  it had only been present transitively through `keithley2600`. Now in both the
  guix `propagated-inputs` and the pyproject dependencies.
- **`typing-extensions`** clarified: it is a *mypy* dependency, so it belongs in
  `native-inputs`/`dev`, not in the runtime dependencies.
- **The mypy configuration moved into `[tool.mypy]`** in `pyproject.toml`, and
  `mypy.ini` was removed.
- **The custom labware definition ships with the package**: it moved to
  `gdnasynth/ot2r/labware/OT2_labware_definition_graphenea_card.json` and is
  resolved with `gdnasynth.ot2r.labware_definition_path(...)` (backed by
  `importlib.resources`), so it no longer depends on the process's working
  directory. A test pins it (`tests/test_labware_definition.py`).
- **Verified by actually building the wheel** (2026-11-09, hatchling 1.27): the
  wheel contains `gdnasynth/ot2r/labware/OT2_labware_definition_graphenea_card.json`
  and contains no `gdnasynth/docs/**` entries.
- **The WIP documents do *not* ship** — they are repository-only.
- **Build backend: hatchling.** Non-Python files inside the package are included
  automatically, which is the whole reason package data mattered here.
  `python-hatchling` was added to the guix `native-inputs`.

## Remaining tasks

- [ ] Keep the guix package (`.guix/gdnasynth.scm`) and the pyproject dependency
  lists in sync by hand — Guix cannot read pyproject, and both files say so.
- [ ] Decide whether the top-level scripts are part of the distribution (see
  below). Not at the moment.

## Decisions and open questions

- **Licence: MIT** (the `LICENSE` file already says so).
- **Python: `>=3.10`.** Development started on 3.10; 3.11 (another machine) and
  3.12.12 (the usual machine) are both known to work.
- **Version pinning: unresolved on purpose.** The project is exploratory and
  nothing is useful to end users yet; scripts are developer tools. Revisit if it
  is ever distributed.
- **The top-level scripts stay where they are for now** (`workflow_gfet_smu*.py`,
  `sweep.py`, `isswisafre.py`, `read_smu_continuously.py`, `fluid_detection.py`,
  `gfet_characteristics.py`, …). They are not shipped.
  - Longer term, if they become worth shipping, move them into the package (e.g.
    `gdnasynth/experiments/`) and expose them as `[project.scripts]` entry
    points. That buys importability (hence testability), removes the dependence
    on the working directory, and gives real `console_scripts`. The cost is that
    they must stop being "run `python3 script.py` from the repo root", so it is
    not worth doing while they are still changing quickly.
- **Dependencies are declared twice** (`pyproject.toml` and the guix package)
  because Guix cannot read the pyproject dependency list; each file carries a
  note to keep the other in sync.
- **Docs packaging.** `exclude = ["gdnasynth/docs/**"]` keeps *all* docs out of
  the wheel. If documentation that should ship is later added under
  `gdnasynth/docs/`, narrow it to `exclude = ["gdnasynth/docs/WIP/**"]` —
  checked on 2026-11-09: that keeps other files under `gdnasynth/docs/` in the
  wheel and still drops the WIP notes.
- **Two stale, untracked scripts** (`demo_maintenance_run.py`,
  `patches/demo_maintenance_run_no_protocol_file.py`) still reference the
  definition by its old root path. They never worked (maintenance runs lacked
  what we needed, and protocol files are incompatible with HTTP-enqueued
  commands), so they are not worth updating.


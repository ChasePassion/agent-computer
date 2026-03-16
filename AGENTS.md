# AGENTS

## Environment

- Primary conda environment for this project: `agent-computer`
- Defined in `environment.yml`
- Created successfully on this machine with:
  - `conda env create -f environment.yml`
- Project dependencies were installed into that environment with:
  - `conda run -n agent-computer python -m pip install -e .`

## Verified Commands

- Run tests:
  - `conda run -n agent-computer pytest -q`
- Import and build the FastAPI app:
  - `conda run -n agent-computer python -c "from agent_computer.api.app import create_app; app = create_app(host='127.0.0.1', port=37688); print(app.title)"`

## Notes

- The project currently targets Python `3.11` via `environment.yml`.
- The local Codex binary is available from the Windows npm global install location when not present on the conda `PATH`:
  - `%APPDATA%\\npm\\codex.cmd`
- New automation or validation commands for this repo should prefer running inside `conda run -n agent-computer ...`.

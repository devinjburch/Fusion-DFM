# Field testing with a local Claude (or by hand)

Fusion runs only on your PC, so testing happens there; results come back through the repo.

## One-time
1. Clone the repo and check out the branch: `git clone -b feature/phase2-manufacturing https://github.com/devinjburch/Fusion-DFM.git`
2. `python scripts\install.py` (installs the add-in and the smoke script), start Fusion, run the add-in.

## Each test round
1. In Fusion: click the button, run **FusionDFMSmoke** (Shift+S → Scripts), run your analyses/comparison/export per [TESTING.md](TESTING.md).
2. In PowerShell in the repo folder: `python scripts\field_report.py --run-tests`
   It writes `docs\field-reports\<timestamp>.md` with: environment, install check (installed files vs the repo), smoke report, log highlights + log tail, recent exports, test results.
3. Open the file, fill in the "What to fill in by hand" section (steps, expected vs actual, screenshots can be attached separately).
4. **Check for private info.** Home-directory paths are replaced with `~`, but design/part names inside logs are not. Edit them out if the repo is public.
5. `git add docs/field-reports && git commit -m "Field report" && git push`, then tell Claude "read the latest field report on feature/phase2-manufacturing".

## Using Claude Code on your PC for steps 2–5
Start it in the clone and give it this prompt:
> Check out `feature/phase2-manufacturing`, pull, and run `python scripts\install.py`. I will then run the smoke test and my analyses in Fusion and tell you when done.
> After that run `python scripts\field_report.py --run-tests`, read the generated file in `docs\field-reports`, summarise any failures, remove any private names, and commit and push only that report.
> Do not change source files unless I ask.

It cannot operate Fusion itself unless you enable desktop/computer-use control; you do the clicking, it does the file work.

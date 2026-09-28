# Published result snapshots

T01–T12 are curated, read-only examples of LensBot output. They preserve the original observations, including unmet targets and uncertain conclusions; inclusion does not mean the optical design passed its requirements.

Each snapshot contains:

- `workflow/intake/request.json` and `params.json`: original request and input parameters.
- `final/`: final lens JSON, Zemax export and layout image.
- `metrics.json`, `evidence.json`, `summary.md`: measured metrics and conclusions.
- `report.html`: standalone report with embedded figures.
- `verification/`: independent Zemax measurements and plots.

Optimization checkpoints, intermediate candidates, agent conversations, event streams, live state and execution manifests remain local and are excluded from Git. These snapshots are not complete resumable runs. Paths or candidate references inside original reports/evidence can refer to omitted local artifacts; use the sibling `final/` files for the published lens. Original machine paths are provenance, not portable commands.

| Example | Report | Summary |
| --- | --- | --- |
| T01 | [Report](T01/report.html) | [Summary](T01/summary.md) |
| T02 | [Report](T02/report.html) | [Summary](T02/summary.md) |
| T03 | [Report](T03/report.html) | [Summary](T03/summary.md) |
| T04 | [Report](T04/report.html) | [Summary](T04/summary.md) |
| T05 | [Report](T05/report.html) | [Summary](T05/summary.md) |
| T06 | [Report](T06/report.html) | [Summary](T06/summary.md) |
| T07 | [Report](T07/report.html) | [Summary](T07/summary.md) |
| T08 | [Report](T08/report.html) | [Summary](T08/summary.md) |
| T09 | [Report](T09/report.html) | [Summary](T09/summary.md) |
| T10 | [Report](T10/report.html) | [Summary](T10/summary.md) |
| T11 | [Report](T11/report.html) | [Summary](T11/summary.md) |
| T12 | [Report](T12/report.html) | [Summary](T12/summary.md) |

## Selecting files for Git

The root `.gitignore` ignores `results/` as a whole. The curated files already tracked by Git remain versioned, so edits to them still appear in `git status`; newly generated files stay untracked. This policy works for any run name and needs no per-experiment ignore rules.

To publish another result, inspect it for credentials, personal information and size, then explicitly add only the selected deliverables. For example, replacing `<run-id>` with the actual directory:

```powershell
git add -f -- results/<run-id>/summary.md results/<run-id>/metrics.json results/<run-id>/report.html
git add -f -- results/<run-id>/final/
git diff --cached --stat
```

Select verification files and input parameters the same way when needed. Avoid force-adding the whole `results/` tree. To stop tracking a previously published file while keeping the local copy, use `git rm --cached -- <file>`; this does not remove it from past commits.

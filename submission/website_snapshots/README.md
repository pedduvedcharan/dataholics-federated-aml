# Saved website versions

| File | What it is | Source commit |
|---|---|---|
| `index_v1_five_sections_64d86a5.html` | The localhost dashboard as a 5-section site (Problem, Architecture, Dashboards with live panels, Demo replay, Judging scorecard), IBM Carbon palette | `64d86a5`, git tag `website-v1-five-sections` |

To restore it: `git checkout website-v1-five-sections -- fedaml/dashboard/static/index.html`, then rebuild the image on the VM.
The page reads `/api/state` and `/api/sar/<id>`, so it only shows data when served by the dashboard app.

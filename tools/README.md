# Tools

| File | Purpose |
|---|---|
| [work_items.json](work_items.json) | work items W-01…W-23 of the [project plan](../docs/plan.md) |
| [create_github_issues.py](create_github_issues.py) | creates labels, milestones and issues from `work_items.json` with the GitHub CLI (dry run without `--apply`) |
| [check_easyeda_netlist.py](check_easyeda_netlist.py) | compares an EasyEDA Pro project (`.epro2`, PCB document) with a reference netlist CSV: missing/extra/renamed parts, wrong or reversed connections, shorts, open nets, LCSC and value differences |

Planned: CAN sniffer/replay (W-05), calibration and production test scripts (W-12, W-20).

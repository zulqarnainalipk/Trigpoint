# Worked examples

Every file here is what a study in the tool produces, saved as JSON, so you can read the output without running anything. They are all made from the **demo roster**, the **demo table of outcomes** and the **demo registry**, which are synthetic: nothing in these files is evidence about a real place. Each file carries `"synthetic": true`.

| File | Study | What to look at |
|---|---|---|
| `overlap_groups.json` | Overlap groups | the pairs, and the groups that mix roles |
| `near_duplicates.json` | Near-duplicate chips | pairs examined and found |
| `domain_shift.json` | Shift between roles | PSI and KS per feature |
| `forecast_validation.json` | Forecast | held-out error against the baseline, interval coverage, what dropping sites would save |
| `grounding.json` | Coordinate grounding | which sites agree with the registry |
| `placement_demo.json` | Placement study | change of the picture and a synthetic gas value with shift |
| `split_certificate.json` | Split certificate | each check with its result and what it found |
| `provenance_demo.json` | Provenance record | the shape of the record |

Rebuild them with `python tools/make_examples.py`. The demo roster deliberately contains two sites that are too close to be in different splits, so the certificate fails; that is the example of what a failure looks like.

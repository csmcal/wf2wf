# Tutorial: CWL → Nextflow Round-Trip

Convert a CWL workflow to Nextflow, edit it, then convert back and verify no information loss.

## 1. Prepare example
```bash
curl -LO https://raw.githubusercontent.com/common-workflow-language/workflows/v1.2/v1.0/v1.2/example_workflows/varscan2/varscan.cwl
curl -LO https://raw.githubusercontent.com/common-workflow-language/workflows/v1.2/v1.0/v1.2/example_workflows/varscan2/varscan-job.yml
```

## 2. Convert CWL → Nextflow
```bash
wf2wf convert -i varscan.cwl -o main.nf --out-format nextflow --report-md
```

## 3. Edit in Nextflow (optional)
Open `main.nf`, change container tag, save.

## 4. Convert back to CWL
```bash
wf2wf convert -i main.nf -o roundtrip.cwl --out-format cwl
```

## 5. Check loss report
```bash
wf2wf validate roundtrip.cwl.loss.json
```
All entries should be `reapplied` — confirming metadata round-tripped.

# Engine Support Matrix

| Engine | Import | Export | Feature Coverage |
|--------|--------|--------|-------------------|
| Snakemake | ✅ | ✅ | Wildcards, resources, conda, containers, run blocks (checkpoints partial) |
| HTCondor DAGMan | ✅ | ✅ | Inline submit, RETRY, PRIORITY, custom ClassAds |
| CWL v1.2 | ✅ | ✅ | Scatter, when, secondaryFiles, expressions |
| Nextflow DSL2 | 🚧 Partial | 🚧 Partial | Processes, basic channels; modules & params TODO |
| WDL 1.1 | ✅ | ✅ | Scatter, runtime; subworkflows limited |
| Galaxy (.ga) | ✅ | ✅ | Basic steps, metadata; advanced collections pending |

Legend: ✅ = fully supported  | 🚧 = basic support, enhancements planned

---

For details on limitations and roadmap see the [design document](https://github.com/csmcal/wf2wf/blob/main/DESIGN.md). 
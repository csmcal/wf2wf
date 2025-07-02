# FAQ

## Do I need Docker installed?
Only if you use `--auto-env build`. Otherwise wf2wf works without Docker.

## Can I skip environment builds?
Yes, pass `--auto-env off`.

## What Python versions are supported?
Python 3.9 – 3.12.

## The conversion reports lost fields – is that bad?
It means the target format can't represent some metadata. The original data are safely stored in `.loss.json` for round-trip.

## Where is the intermediate JSON stored?
By default it's kept in memory; use `wf2wf convert ... --export-ir ir.json` (planned) to write it. 
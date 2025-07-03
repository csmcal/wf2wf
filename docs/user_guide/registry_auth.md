# Pushing & Pulling Container Images

`wf2wf` can push OCI images it builds via `--auto-env build` to a registry.

## Common registries

| Registry | Push URL | Auth method |
|----------|----------|-------------|
| GitHub Container Registry (GHCR) | `ghcr.io/<org>/<image>` | `echo $CR_PAT | docker login ghcr.io -u USERNAME --password-stdin` |
| Docker Hub | `docker.io/<user>/<image>` | `docker login` |
| Amazon ECR | `<aws_account>.dkr.ecr.<region>.amazonaws.com/<repo>` | `aws ecr get-login-password | docker login --username AWS --password-stdin …` |
| Google Artifact Registry | `us-central1-docker.pkg.dev/<proj>/<repo>/<image>` | `gcloud auth configure-docker` |

## CLI flags
```bash
wf2wf convert … --auto-env build --push-registry ghcr.io/myorg
```

If `--push-registry` is omitted, images stay in the local daemon.

### Private registries
Set username/password via standard Docker config or use:
```bash
docker login <registry>
export WF2WF_REGISTRIES=<registry>
```
`wf2wf` will probe all registries listed in the env var for existing images before building anew.

### Troubleshooting pushes
* 403 Forbidden – token lacks `write:packages` (GHCR) → regenerate PAT.
* connection timeout – corporate firewall → use proxy or mirror registry.
* manifest invalid – disable experimental features if using rootless Docker.

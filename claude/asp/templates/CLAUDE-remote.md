


---

## Remote Execution

This project targets **{{target}}** for remote execution via SSH.

**IMPORTANT: Do NOT run `python`, `pip`, `conda`, or `jupyter` locally.**
All computation must go through `asp remote exec`. A PreToolUse hook enforces
this — direct local execution will be blocked automatically.

### Architecture

- **SSH/SFTP** handles all remote operations: file transfer, command execution,
  job submission (sbatch), status queries (sacct), and result download
- Uses sshproxy certificates for NERSC authentication
- Remote workdir is configured in `remote.yaml`

### Interactive Workflow

Use `asp remote` commands to work with the cluster interactively:

```bash
# 1. Check connectivity
asp remote status

# 2. Push local files to the cluster
asp remote push

# 3. Run commands on the cluster
asp remote exec -- python steps/main.py
asp remote exec -- ls results/
asp remote exec --push -- bash run.sh   # push files first, then execute

# 4. Submit a batch job (for long-running work)
asp remote submit --script job.sh --universe baseline

# 5. Track job status
asp jobs list
asp jobs status <job_id>
asp remote log <job_id>         # view stdout
asp remote log <job_id> --err   # view stderr

# 6. Pull results back
asp remote pull --universe baseline
asp remote pull --job-id <job_id>
```

### What Gets Pushed

`asp remote push` uploads these to the remote workdir:
- `asp.yaml`, `remote.yaml`
- `universes/`, `steps/`, `workflows/`

Results are excluded (they flow in the other direction via `asp remote pull`).

### Writing Batch Scripts

Write your own batch scripts for `asp remote submit`. The script runs in the
remote workdir, so paths are relative to that:

```bash
#!/bin/bash
#SBATCH --time=01:00:00
#SBATCH --nodes=1

python steps/main.py
```

### Cluster Management

```bash
asp remote setup     # Configure a new cluster in ~/.asp/remotes/
asp remote status    # Check SSH connection
```

### Configuration

Cluster details are in `remote.yaml` (copied from `~/.asp/remotes/` by `asp init --target`).

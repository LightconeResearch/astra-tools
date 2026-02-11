# NERSC Perlmutter

[Perlmutter](https://docs.nersc.gov/systems/perlmutter/) is a GPU-accelerated supercomputer at the National Energy Research Scientific Computing Center (NERSC).

## Prerequisites

- A NERSC account ([request one here](https://iris.nersc.gov/train/signup.php))
- An active allocation/account (e.g. `m1234`)
- Multi-factor authentication set up on your NERSC account

## Setup

```bash
asp remote setup perlmutter
```

This interactive command will:

1. **Prompt for your credentials** — NERSC username, allocation, and working directory
2. **Install sshproxy** — downloads and installs the NERSC [sshproxy](https://docs.nersc.gov/connect/mfa/#sshproxy) tool if not already present
3. **Generate an SSH certificate** — runs `sshproxy -u <username>`, which prompts for your NERSC password + one-time code (OTP from your authenticator app)
4. **Test SSH connectivity** — verifies the connection to `perlmutter.nersc.gov`
5. **Save config** — writes `~/.asp/remotes/perlmutter.yaml` for reuse across projects

## SSH certificates

NERSC uses short-lived SSH certificates instead of permanent keys. The certificate at `~/.ssh/nersc` lasts **24 hours**.

When it expires, any ASP remote command will tell you:
```
NERSC SSH certificate expired 3h 42m ago (at 2025-01-15 14:30 UTC).
Renew with: sshproxy -u <username>
```

Run the `sshproxy` command shown, enter your password + OTP, and you're good for another 24 hours. You do **not** need to re-run `asp remote setup`.

### Manual certificate renewal

```bash
sshproxy -u <username>
# Enter Password+OTP when prompted
```

This creates/refreshes three files:
- `~/.ssh/nersc` — private key
- `~/.ssh/nersc.pub` — public key
- `~/.ssh/nersc-cert.pub` — signed certificate (24h validity)

## Working directory

The default working directory is `/pscratch/sd/<first_letter>/<username>/asp`. This is on Perlmutter's scratch filesystem (`$PSCRATCH`), which is:

- **Fast** — Lustre parallel filesystem, good for I/O-heavy workloads
- **Not backed up** — files are purged after 90 days of inactivity
- **Shared** — accessible from all Perlmutter nodes

If you need persistent storage, change the workdir during setup to a location under `/global/cfs/cdirs/<project>/`.

## Slurm defaults

The default job settings in `config.yaml`:

| Setting | Default | Description |
|---------|---------|-------------|
| `qos` | `regular` | Quality of service ([options](https://docs.nersc.gov/jobs/policy/)) |
| `constraint` | `cpu` | Node type (`cpu` or `gpu`) |
| `time` | `00:30:00` | Wall clock limit |
| `nodes` | `1` | Number of nodes |

Override these per-project by editing `remote.yaml` after `asp init --target perlmutter`.

## Useful links

- [NERSC documentation](https://docs.nersc.gov/)
- [Perlmutter architecture](https://docs.nersc.gov/systems/perlmutter/architecture/)
- [Job submission guide](https://docs.nersc.gov/jobs/)
- [sshproxy documentation](https://docs.nersc.gov/connect/mfa/#sshproxy)
- [Scratch filesystem policy](https://docs.nersc.gov/filesystems/perlmutter-scratch/)

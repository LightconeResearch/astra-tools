#!/bin/bash
# PreToolUse hook: Block direct Python/pip execution in remote-targeted projects.
# When remote.yaml exists, computation should happen on the cluster via
# "asp remote exec" — not locally.

input=$(cat)

# Only check if this project has a remote target
if [ ! -f "remote.yaml" ]; then
    exit 0
fi

command=$(echo "$input" | jq -r '.tool_input.command // empty')
if [ -z "$command" ]; then
    exit 0
fi

# Extract the first token (the actual binary being invoked).
# Handle leading env vars, semicolons after prior commands, etc.
# We strip common prefixes and grab the first word that looks like a command.
first_cmd=$(echo "$command" | sed 's/^[A-Z_]*=[^ ]* *//' | awk '{print $1}')
base=$(basename "$first_cmd")

# Allow "asp remote exec -- python …" — the whole point.
if echo "$command" | grep -qE '^\s*asp\s+remote'; then
    exit 0
fi

# Blocked commands: direct Python / pip / conda / jupyter execution
case "$base" in
    python|python3|python3.*|pip|pip3|conda|jupyter|ipython)
        # Read target name from remote.yaml for a helpful message
        target=$(grep -m1 '^target:' remote.yaml 2>/dev/null | awk '{print $2}')
        target=${target:-"the remote cluster"}

        reason="This project targets $target for remote execution. Run Python on the cluster instead:\n\n  asp remote exec -- $command\n\nOr push files first:\n\n  asp remote exec --push -- $command\n\nSee CLAUDE.md § Remote Execution for the full workflow."

        # Return structured deny
        escaped=$(printf '%s' "$reason" | jq -Rs .)
        cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": $escaped
  }
}
EOF
        exit 0
        ;;
esac

# Everything else (asp, git, ls, cat, etc.) is fine.
exit 0

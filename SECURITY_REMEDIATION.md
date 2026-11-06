# Security remediation

## Confirmed exposure

The public repository contains a historical backup configuration with populated credentials for five site accounts and a dashboard password. Treat every credential in that backup as compromised.

The tracked SQLite files use a schema that stores session cookies and session payloads. The audit utility reports counts only and never prints cookie, token, username, or password values.

## Required account actions

1. Change the passwords for all five affected site accounts.
2. Revoke active sessions for those accounts at the corresponding sites where possible. Password changes do not universally invalidate every existing session.
3. Set a new dashboard password locally using GOLF_UI_PASS or the ignored in/config/config.local.ini file. Do not reuse the exposed dashboard password.
4. Keep proxy credentials and local account configuration out of Git.

## Database persistence

The scheduled GitHub Actions workflow does not commit data/base.db between runs. Its durable release-history state is viewer/public/bonus-history.json, which the workflow explicitly commits. SQLite is a runtime cache for a single runner invocation and a local store for interactive runs. A separate cloud database or encrypted artifact migration is not needed for the scheduled history pipeline.

After the tracked database is removed, GitHub Actions creates a fresh local database at runtime. Local databases remain under data/, are ignored by Git, and are created with owner-only file permissions where supported.

## Git history purge

Deleting files in a normal commit does not erase earlier versions. After credentials have been rotated, rewrite the public repository history to remove the backup directory, tracked database, archive, generated logs/bytecode, and all historical versions of in/config/config.ini. Preserve and restore only the current blank config template.

History rewriting changes commit IDs, requires a force push, and breaks existing clones. Use a fresh clone and git-filter-repo, then force-update all intended branches and tags. GitHub may retain cached views or pull-request references after a rewrite; contact GitHub Support to request complete sensitive-data removal for the affected commit/blob references.

## Dashboard security changes

- API authentication is mandatory and fails closed.
- Incorrect credentials return HTTP 401.
- Config responses expose only editable delay settings, never account sections or secrets.
- Config writes are restricted to validated delay values.
- WebSocket connections require a short-lived, single-use ticket from an authenticated API request.
- The dashboard binds to 127.0.0.1 by default. Set GOLF_BIND_HOST only for an intentional trusted-network deployment protected by appropriate transport security.

# 026: Platform-controlled administrator access recovery

- **Status:** accepted by Captain directive
- **Date:** 2026-09-09
- **Assignment:** Implement issue 17, providing recovery when the console admin password is lost.
- **Lane:** Firstmate direct dispatch
- **Workers dispatched:** None (directive authority)
- **Authority:** Captain directive, 2026-09-09: accept recovery ceremony option 1, preserve API keys, invalidate every admin session, and show a persistent recovery notice.

## Context

The appliance hashes its first admin password immediately and has no default or retained plaintext credential. That first-run posture is intentional, but it previously left no recovery path for an operator who lost the password.

This is a directive-authority record because the Captain selected the recovery ceremony and its key and session effects directly. No worker proposal round ran.

## Decision

Recovery requires platform control of the appliance. The platform owner places a one-line UTF-8 password file at `/keys/admin_recovery_password`, owned by the service user with mode `0600`, while the appliance is stopped. The application inspects this distinct path only during process startup. There is no network recovery route, default password, Docker socket, or cluster credential inside the appliance.

The recovery path reuses the first-run bootstrap foundation where its properties fit: private regular-file validation, scrypt hashing, minimum password length, and removal after use. It uses a different filename and a startup-only call path so a bootstrap file left from an older deployment cannot reset an initialized appliance. Recovery refuses an empty, multiline, invalid UTF-8, oversized, wrongly owned, or group-readable or world-readable file. Unlike general persistent keys, the recovery file is not permission-repaired because its exact owner-only mode is part of the deliberate ceremony.

In one immediate SQLite transaction, successful recovery replaces the admin hash, increments the persistent admin-session generation, records `admin_password_recovered`, and stores the recovery time for the console notice. Every authenticated console request compares its cookie generation with the database generation, so all sessions created before recovery fail on their next request. API-key rows and encrypted backend credential envelopes are not read or changed.

After validation, the recovery file is removed before the database transaction begins. This makes the file a single-use act even if the process fails later. If removal fails, the password hash and session generation remain unchanged and startup reports a degraded state. If the later database transaction fails, the prior password remains valid and the operator must stage a new recovery file before trying again.

The first successful login after recovery shows a persistent notice with the recovery time and the session and API-key effects. An authenticated CSRF-protected dismissal removes that notice and records `admin_recovery_notice_dismissed` in the same durable configuration event ledger.

## Dissent

None. The implementation follows a direct Captain decision.

## Protected paths touched

`src/vcf_mcp/`

## Sign-offs

Directive-authority record: no worker round produced this decision, so it has no worker sign-off lines. The `Authority` field above stands in their place.

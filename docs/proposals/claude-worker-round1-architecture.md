# claude-worker, round 1 architecture proposal

Phase-1 blind proposal. Written without reading any peer proposal, branch,
worktree, or inbox.

## 0. What I actually measured

I did read-only recon against DEVEL
(`vcf-lab-operations-devel.int.sentania.net`, confirmed by an assertion in
the recon script that the resolved host contains `devel`). Every request was
a GET except the documented auth token acquire. I ran no POST against any
action endpoint. No credential value was printed, logged, or committed;
credentials came from vcf-content-factory's existing `devel` profile via
`VCFOpsClient.from_env(profile='devel')` and never left the process.

Numbers below are load-bearing for the recommendations, so here they are up
front:

| Measurement | Value |
| --- | --- |
| `/api/versions/current` | `releaseName` "VCF Operations 9.0.2.0", `major` 2, `minor` 2, `buildNumber` 25137838 |
| `GET /api/actiondefinitions` | HTTP 200, `totalCount` **142**, 43,009 bytes |
| Distinct `contextResourceKindKey` | 10 |
| Distinct `actionAdapterKindKey` | 5 (APPOSUCP 76, VMWARE 62, ManagementPackBuilderAdapter 2, SupervisorAdapter 1, APPLICATIONDISCOVERY 1) |
| Distinct `displayName` across 142 defs | **66** |
| `type` field across all 142 defs | `UPDATE`, for every single one |
| Parameter metadata present in the list response | **none** |
| `/api/resources` totalCount | 508 (a small lab) |
| `/api/resources?pageSize=5000` raw | 1,097,361 bytes (~274k tokens) |
| Same 508 resources, field-projected | 96,357 bytes (~24k tokens), **92% reduction** |
| Share of the raw resource payload that is HATEOAS `links` | **53%** |
| `/api/alerts` totalCount | 1,113 |
| `/api/reportdefinitions` | 74 defs, 114,293 bytes |
| `/api/supermetrics` | 66, 52,485 bytes |
| Live Swagger/OpenAPI on the appliance | **not served**: 404 at `/suite-api/docs/swagger.json`, `/v2/api-docs`, `/api-docs`, `/docs/openapi.json` |
| `/suite-api/internal/*` without `X-Ops-API-use-unsupported` | HTTP 403, **HTML body**, not JSON |
| Bogus token | 401, JSON `{"type":"Error","message":"...auth scheme \"vRealizeOpsToken\"...","httpStatusCode":401,"apiErrorCode":1512}` |
| `Authorization` scheme accepted | **both** `vRealizeOpsToken` and `OpsToken` return 200; `Bearer` returns 401 with an **HTML** body |

Two of those deserve calling out because they contradict what I expected
going in:

1. I expected to find a SPEC error in the `Authorization: OpsToken` line
   (SPEC section 2), because vcf-content-factory's `client.py` sends
   `vRealizeOpsToken`. I tested both against devel. **Both are accepted**, and
   Broadcom's own VCF 9.0 documentation
   (`vcf-content-factory/reference/docs/vcf9/suite-api.md`) settles which is
   which: `OpsToken` is canonical for 9.x and `vRealizeOpsToken` is a
   supported legacy alias. So the SPEC is not merely defensible, it is
   correct and `client.py` is the one using the legacy form. I am not
   proposing an amendment, and I would send `OpsToken`. I am recording that I
   had this backwards before I checked, because "the shipping client must be
   right" is exactly the assumption a peer could inherit from me.
2. The assignment hoped the appliance might serve its own Swagger. On 9.0.2
   it does not. Fork 6 therefore cannot lean on live schema introspection,
   and I have designed it accordingly.

I also stood up a throwaway venv in `/tmp` with `mcp==1.28.1` to check fork
2's claims against the real package rather than from memory. Nothing was
added to any manifest in this repo, per the constraint.

---

## 1. Approach

### Fork 1: static core tools plus one action dispatcher. Not dynamic generation.

**Recommendation: 14 static tools total, of which 4 cover the entire action
framework. No tool is ever generated from the catalog.**

The catalog data kills dynamic generation outright, and not for the reason I
expected (tool-count explosion). It kills it for a structural reason:

**`GET /api/actiondefinitions` contains no parameter metadata.** The 142
returned objects have exactly nine keys: `id`, `displayName`, `type`,
`actionAdapterKindKey`, `contextAdapterKindKey`, `contextResourceKindKey`,
`contextIds`, `scheduleEnabled`, `canRecommend`. There is no
`methodParameters`, no `actionContext.fields`, no type information about
what the action takes. I verified this across all 142 records, not just a
sample.

Parameter metadata lives only in the response to
`POST /api/actions/{id}/query`, and that call **requires a
`contextResourceId`** in its body: you must already have picked a concrete
target resource before the API will tell you what the parameters are. The
returned `methodParameters` and `actionContext.fields` are populated *for
that resource*.

So to generate a faithful JSON Schema for a dynamically-created tool, the
server would have to, at tool-registration time, pick an arbitrary resource
of the right kind for each of 142 actions and issue 142 POSTs to a
populate endpoint, on a live appliance, before it can answer a single
`tools/list`. That is: 142 extra round trips per target per refresh; a
schema derived from whichever resource happened to be picked, which is not
guaranteed to generalise; and a POST storm against an appliance during what
the client thinks is a read. It is the wrong shape at every level, and the
read-only-by-default invariant makes "POST to discover" especially ugly.

The secondary arguments are also decisive on their own:

- **Name collisions, and the reason for them is structural.** 142 definitions
  carry only 66 distinct `displayName`s. The catalog returns **one entry per
  (action x ResourceContext) pair**, so "Power Off VM" appears once per
  context resource kind it applies to, with the entries differing only in
  `contextResourceKindKey`. A generation scheme keyed on display name emits
  three identically-named tools for the same action. Keying on `id` instead
  yields tool names like
  `VMWARE-Set_CPU_Count_and_Memory_for_VM_Power_Off_Allowed`, which no model
  reasons about well, and still does not disambiguate the contexts. There is
  no naming scheme that makes this catalog into a good tool list.
- **The action id contains a literal space.** Ids are
  `{adapterKindKey}-{actionKey}`, for example `VMWARE-Power Off VM`. It must
  be URL-encoded on every path interpolation into
  `/api/actions/{id}`, and `GET /api/actions` (the bare collection) is a 404,
  only the sub-paths exist. Neither is a fork-deciding fact, but both are the
  kind of thing that costs an afternoon, so they belong in the design rather
  than in a debugging session.
- **Signal-to-noise.** 76 of 142 are APPOSUCP "Configuring \<app\> plugin"
  actions (Configuring Cassandra plugin, Configuring Riak plugin, Configuring
  WebLogic plugin, and so on) targeting `Endpoint` resources. These are
  Application Monitoring agent-plugin config, essentially irrelevant to the
  VCF operational workflows this server exists for. Generating 76 tools
  nobody will call, into every client's context, on every session, is a pure
  tax.
- **Context cost.** At a conservative 120 tokens per generated tool
  definition, 142 tools is ~17k tokens of `tools/list` before the client has
  done anything. VCF Private AI Services is the consumer we understand least
  and can least afford to stress; a 14-tool surface is one it will tolerate
  and a 142-tool surface is a gamble on an unknown.
- **`type` is `UPDATE` for all 142.** There is no read-only subset of the
  action catalog to safely auto-expose. The field cannot be used to
  distinguish safe from unsafe, which means any generation scheme needs a
  hand-maintained allowlist anyway. Once you have the allowlist, generation
  has bought you nothing.

**What I would build.** Module layout under `src/vcf_ops_mcp/`:

```
server.py          builds the ASGI app, mounts MCP + admin UI on one listener
tools/
  targets.py       list_targets
  inventory.py     list_adapter_kinds, list_resource_kinds, find_resources,
                   get_resource
  metrics.py       get_latest_stats, query_stats, list_stat_keys,
                   list_super_metrics
  alerts.py        find_alerts, get_alert
  reports.py       list_report_definitions, run_report, download_report
  actions.py       list_actions, plan_action, apply_action, get_action_task
  skills.py        list_skills, get_skill
ops/
  client.py        per-target async suite-api client, token lifecycle
  catalog.py       action catalog cache
  projection.py    response field projection (see below)
registry/          target registry + encrypted credential store
audit/             audit log writer
admin/             Starlette admin UI
```

**Client hardening, which `ops/client.py` owns and which the reference
`client.py` does not do.** vcf-content-factory's client is the right model
for the token dance and I would port it, but it has two gaps that matter far
more for a long-lived server than for a CLI:

- **It sets no request timeout at all**, so a call can hang indefinitely.
  An MCP server that hangs is worse than one that errors, because the client
  is an agent loop that will sit there. Every suite-api call gets an explicit
  connect and read timeout.
- **It re-authenticates reactively on 401 only.** The acquire response
  carries `validity` as an absolute epoch-ms expiry (the token is good for
  6 hours, sliding, extended on each call, with no refresh-token concept), so
  I would refresh proactively at ~80% of remaining validity and keep the
  401-retry as the backstop rather than the primary mechanism. I would also
  call `POST /api/auth/token/release` on shutdown and on target
  deregistration, which the reference client never does.
- **403 and 401 mean different things here**: a missing `Authorization`
  header is 403, an invalid or expired token is 401, and an expired token is
  indistinguishable from a bad one in the body. So the retry trigger is the
  status code, and the retry happens exactly once.
- **Error bodies are not reliably JSON.** I observed HTML bodies on both the
  `/suite-api/internal/*` 403 and the `Bearer`-scheme 401. Any
  `response.json()` in the error path needs a guard. The documented error
  schema (`type`, `message`, `httpStatusCode`, `apiErrorCode`) guarantees
  only `message`.
- **429 is documented and never observed.** The vendor spec documents rate
  limiting with no `Retry-After` semantics, and there is no observed 429
  anywhere in the lab's knowledge base, so no shipping client handles it.
  I would implement exponential backoff for it anyway and log loudly the
  first time it fires, because an agent loop is exactly the traffic shape
  that would find the limit first.
- **TLS verification defaults to on, per target, as an explicit admin-UI
  setting.** Broadcom's own in-appliance `SuiteAPIClient` sets
  `verify(false)` and `ignoreHostName(true)`, and that posture is documented
  in the lab's lessons as sanctioned for adapters running inside the
  appliance and explicitly not to be copied into external code. We are
  external code reaching a target over the network. SPEC 4.3 already lists
  verify-SSL as a per-target field; I am naming the default as on.

The four action tools:

- **`list_actions(target, resource_kind=None, adapter_kind=None, q=None)`**
  reads the cached catalog and returns a *filtered, projected* list:
  `id`, `displayName`, `contextResourceKindKey`, and a computed
  `risk` label. Never returns all 142 unfiltered; if a call would return
  more than 25, it returns the first 25 plus a `truncated` count and the
  available filter facets. The catalog is cached per target with a 15-minute
  TTL, refreshed lazily on read, and is a single 43 KB GET to refill.
- **`plan_action(target, action_id, resource_ids, parameters=None)`** calls
  `POST /api/actions/{id}/query`, and returns a plan object: the resolved
  action, the resources it would touch (by name and id, not just uuid), the
  `methodParameters` with which are required, any `actionContext.fields`
  values the appliance populated, the exact `action-execution` body that
  would be submitted, and a server-minted `plan_id`. **It does not execute.**
  The `plan_id` is a signed token over a hash of the execution body, with a
  short TTL (I would start at 10 minutes).
- **`apply_action(target, plan_id, confirm=True)`** takes only a `plan_id`.
  It re-derives the execution body from the stored plan, checks the hash
  still matches, checks the target is actions-enabled, checks the key scope
  is actions-capable, checks the action id is on the allowlist, writes the
  audit record, then POSTs `/api/actions/{id}`. **`apply_action` cannot take
  a raw action body.** This is the important design property: there is no
  code path from an MCP client to `POST /api/actions/{id}` that does not go
  through a plan the server itself generated. Plan-then-apply is enforced by
  the type signature, not by convention.
- **`get_action_task(target, task_id)`** polls `GET /api/actions/{taskId}/status`
  and projects the response down to `state`, `startDate`, `completeDate`, and
  ERROR/WARN messages, dropping the per-object noise unless asked.

**The allowlist.** A checked-in `actions-allowlist.yaml` naming the action
ids the server will ever execute, seeded from the VMWARE subset that matters
(Power On VM, Power Off VM, Shut Down Guest OS for VM, Reboot Guest OS For VM,
Set Memory for VM, Set CPU Count for VM, Delete Unused Snapshots for VM, Set
DRS Automation). Everything else is visible to `list_actions` with
`executable: false`, so the model can see the capability exists and say so,
but `apply_action` refuses it server-side. Adding to the allowlist is a PR
against a protected path, which is the right friction for widening action
blast radius.

**Projection is the other half of fork 1, and I think it is underweighted in
the framing.** The measured numbers make this concrete: 508 resources is
1.07 MB raw, of which 53% is HATEOAS `links` blocks that are pure waste to a
language model, and projecting to six fields gets the same information into
96 KB. That is 274k tokens versus 24k. On a real customer-scale appliance
this is the difference between a working server and one that cannot answer.

And the API's own defaults are actively hostile here: **`pageSize` defaults
to 1000 across all 35 paginated public endpoints, with no declared maximum.**
A tool that forgets to set it explicitly gets 1000 records. The lab has 1,113
alerts, 74 report definitions, and (per vcf-content-factory's recon against a
larger instance) 1,491 alert definitions and 2,217 symptom definitions, each
carrying nested condition trees. `alertdefinitions` and `symptomdefinitions`
are the worst offenders on the public surface and neither is in my MVP tool
list, which is partly why.

So `ops/projection.py` is a first-class module, not a helper. The rules:
every tool declares a default projection; the client layer sets an explicit
`pageSize` on every list call and **never** inherits the API default; tools
cap it server-side (25-50) regardless of what the client asks; every list
response returns `pageInfo.totalCount` so the model knows what it is not
seeing, plus a cursor for the next page rather than auto-paginating; and
there is a `fields=` escape hatch. No tool returns a raw suite-api body, and
report downloads return a handle rather than inlined binary.

**Why not the hybrid.** A hybrid (static core plus generated tools for a
small curated subset) is the tempting middle, and I am rejecting it
deliberately rather than by omission. It buys a marginally nicer signature
for a handful of actions and costs: a second code path into action
execution that does not go through `plan_id`, generated schemas that still
need the populate-call problem solved, and a tool surface that changes shape
depending on what the appliance happens to have installed, which makes
client-side caching and audit-log analysis both harder. The cost is
structural and the benefit is ergonomic. I would not take that trade for
the safety-critical surface of this server.

### Fork 2: the reference MCP Python SDK (`mcp`), not the separate FastMCP package.

**Recommendation: `mcp` 1.28.x. One direct dependency.**

The fork as posed is partly a false dichotomy, and I want to be precise
about why rather than assert it. I installed `mcp==1.28.1` and checked:

- The reference SDK **ships FastMCP**, as `mcp.server.fastmcp.FastMCP`. This
  is the donated FastMCP 1.x lineage. The decorator ergonomics that make
  people want FastMCP are already in the reference SDK.
- `FastMCP.streamable_http_app()` exists and **returns a Starlette
  application**. That is exactly what SPEC section 4 requires: "three
  surfaces on one listener". I can mount the MCP app and the admin UI in one
  ASGI app, one uvicorn process, one container, no reverse-proxy gymnastics
  inside the image.
- `FastMCP.__init__` takes a `token_verifier`, and `TokenVerifier` is a
  one-method protocol: `async def verify_token(self, token) -> AccessToken | None`.
  `AccessToken` carries `client_id`, `scopes`, and a `claims` dict. That is a
  near-exact fit for the API-key model in fork 3: `client_id` is the key id,
  `scopes` carries `read_only` or `actions`, `claims` carries the permitted
  target list. I do not have to write bespoke middleware or fight the
  framework; the extension point is already the right shape.

And the transitive dependency picture decides it. Installing `mcp` alone
pulls in `starlette`, `uvicorn`, `httpx`, `pydantic`, `pydantic-settings`,
and **`cryptography`**. So choosing the reference SDK gives me the HTTP
server, the async HTTP client for talking to suite-api, the settings layer,
and the credential-store crypto library, all as transitive deps of a single
direct dependency. The only additional direct dependency my whole proposal
needs is `jinja2` for the admin UI templates.

Against the separate FastMCP package: it is at 3.4.x and has gone through
1.x, 2.x, and 3.x major versions. It is a fast-moving third-party project
tracking a fast-moving protocol. For a server whose safety properties are the
point, I want the dependency that is maintained in lockstep with the spec by
the people who write the spec, and I want fewer moving parts under the
action-execution path. FastMCP 3.x has features I do not need (server
composition, proxying, generated OpenAPI servers) and each of them is
surface area. If we later find the reference SDK genuinely cannot do
something, the migration is mostly decorator-compatible because of the shared
lineage, so this is a reversible decision made in the cheap direction.

**Auth wiring.** A `VcfOpsTokenVerifier` implementing `TokenVerifier`, doing
the key lookup described in fork 3, plus one thin Starlette middleware ahead
of the MCP mount for the audit-log write and request id. Scope enforcement
happens in two places on purpose: at the verifier (so an unscoped key never
gets an `AccessToken` with `actions`) and again inside `apply_action` (so a
bug in the middleware chain does not become an action execution). Defence in
depth on the one path where it matters.

### Fork 3: AES-256-GCM with a keyring file for target credentials; HMAC, not Argon2, for API keys.

Two different problems that the fork framing bundles together. They want
different answers.

**Target credentials (VCF Ops passwords).** These must be *reversibly*
encrypted, because the server has to replay them to `POST /api/auth/token/acquire`.

- **Algorithm: AES-256-GCM** via `cryptography`'s `AESGCM` (already a
  transitive dep, so no new dependency). Not Fernet: Fernet is
  AES-128-CBC + HMAC, it has no AAD support, and AAD is the feature I
  specifically want.
- **AAD binds ciphertext to its row.** Each encrypted field is stored with
  AAD = `f"{target_id}|{field_name}|{key_id}"`. This means a ciphertext
  lifted from the prod target's row and pasted into the devel target's row
  fails to decrypt rather than silently working. Given the constitution's
  prod hard-block, making credential material non-transplantable between
  target rows is worth the two lines it costs.
- **Nonce: 96-bit, from `os.urandom`, fresh per encryption, stored beside
  the ciphertext.** Never derived, never reused.
- **Key file: a JSON keyring**, not a bare key. `{"active": "k2", "keys":
  {"k1": "<b64>", "k2": "<b64>"}}` at `/data/keys/credstore.json`, mode
  0600, owned by the app uid, created on first boot if absent. Every
  ciphertext record stores its `key_id`.
- **Rotation story, which the bare-key design does not have.** Add a new key,
  flip `active`, and a background sweep re-encrypts records tagged with the
  old key id. Decryption always works during the sweep because records
  carry their own key id. When the sweep reports zero records on the old
  key, the admin UI offers to drop it. Rotation is therefore online and
  interruptible, and a half-finished rotation is a valid state rather than
  an outage. Rotation is exposed as an admin UI button, because a rotation
  story that requires a shell on the container host is a rotation story
  nobody executes.
- **The key file is a file on a volume, not an environment variable, and
  that is deliberate.** The files-hosting service has a documented,
  twice-encountered bug where a `$`-bearing secret got silently truncated
  passing through shell sourcing and Compose `${VAR}` interpolation,
  producing a deploy that looks healthy and fails every credential check. A
  base64 key can contain `$`... actually base64 cannot, but the general
  lesson holds and the SPEC already mandates a key file. I would additionally
  copy files-hosting's defence: the app **refuses to boot** if the keyring
  file exists but does not parse, rather than regenerating it, because
  silently regenerating a keyring means silently orphaning every stored
  credential.

**API keys.** These must *not* be reversible. The server never needs to show
a key again after minting.

- **Format: `vom_<key_id>_<secret>`** where `key_id` is 8 url-safe chars and
  `secret` is `secrets.token_urlsafe(32)` (256 bits). The `key_id` prefix is
  stored plaintext and indexed, so verification is a single indexed lookup
  rather than a scan over every key.
- **Storage: HMAC-SHA256(secret, pepper), constant-time compared.** The
  pepper is a separate entry in the keyring file, so a database file leak
  without the key file yields nothing.
- **Explicitly not Argon2id, and this is the part I expect to be attacked.**
  Argon2 exists to make low-entropy human-chosen passwords expensive to
  brute-force. These keys are 256 bits of CSPRNG output; there is no
  dictionary, and no attacker is brute-forcing a 256-bit random token
  regardless of hash cost. What Argon2 would actually buy is 50-100 ms of
  latency on **every single MCP tool call**, on a server whose whole job is
  many small calls in an agent loop. That is a real cost for a defence
  against an attack that does not exist against this input. Argon2id *is*
  the right answer for the admin UI's human-chosen bootstrap password, and
  I use scrypt/Argon2 there (fork 4). Different input entropy, different
  answer.
- **Scope model: two scopes, not a permission matrix.** `read_only` and
  `actions`, where `actions` implies `read_only`. Plus an orthogonal
  per-key **target allowlist** (a list of target ids, or `*`). So a key is
  "read-only on all targets" or "actions on devel only". I am deliberately
  refusing a per-tool or per-action permission model: it is more expressive
  and it is the kind of expressiveness that produces a misconfiguration
  nobody notices. The blast radius is already bounded by the per-target
  actions toggle and the action allowlist; a third overlapping mechanism
  adds confusion, not safety.
- **Minting shows the key exactly once**, in the admin UI, with no
  retrieval path. Revocation is immediate (delete the row, plus a small
  in-process cache with a short TTL so revocation is not defeated by
  caching; I would cap that cache at 60 seconds).

**Escalation flag.** I do not think fork 3 needs escalating; it does not
widen the action blast radius and the SPEC already fixes the shape
("app-managed key file, 0600"). But the *specific choice* of two scopes
rather than a finer model is a policy call about who can do what, and if
Scott wants a finer grain that is his call to make, not the team's. I have
proposed the coarse model and flagged it rather than escalating the whole
fork.

### Fork 4: Starlette plus Jinja2, server-rendered, in the same process. Port the files-hosting pattern, not its code.

**Recommendation: server-rendered, no SPA, no build step. But Starlette,
not Flask.**

The lab precedent is real and I want to take as much of it as survives
contact with fork 2. What files-hosting actually does: Flask 3.0 + Jinja2,
signed-cookie session holding a single `authenticated` boolean, no session
store, no user table, Werkzeug `scrypt` hash supplied as an env var with the
app refusing to boot without it, `SESSION_COOKIE_HTTPONLY` +
`SECURE` + `SameSite=Strict`, ~350 lines of hand-written vanilla JS and CSS
with no dependencies, gunicorn on a digest-pinned `python:3.12-slim`, uid
pinned to the host deploy account.

Almost all of that is right and I would copy it. The one piece that cannot
come across is Flask itself. Flask is WSGI; the MCP Streamable HTTP endpoint
is ASGI. SPEC section 4 says one listener for all three surfaces. Mounting
WSGI inside ASGI needs an adapter and gives up async in the admin handlers
(which do need to make async suite-api calls, for example to verify a target's
credentials at registration time). Running two processes gives up "one
listener" or adds an in-image proxy. So: **Starlette + Jinja2**, which is the
same architecture as files-hosting expressed in the framework fork 2 already
brings in for free.

Concretely:

- One ASGI app. `Mount("/mcp", mcp.streamable_http_app())`,
  `Mount("/admin", admin_app)`, `Route("/healthz", ...)`. One uvicorn.
- `SessionMiddleware` (signed cookie), `httponly`, `secure`, `samesite=strict`,
  14-day lifetime. Session payload is one boolean, as in files-hosting. No
  user table.
- **Bootstrap admin credential: an scrypt or Argon2id hash supplied as
  `VCFOPS_MCP_ADMIN_PASSWORD_HASH`, generated out-of-band by a
  `python -m vcf_ops_mcp.hashpw` CLI, with the app refusing to boot if it is
  absent or malformed.** This is exactly files-hosting's pattern including
  its hash-shape validation guard, which exists because that hash got
  silently truncated twice by two unrelated mechanisms. I read SPEC 4.3's
  "bootstrap admin credential provisioned at first deploy, stored hashed" as
  satisfied by this, and I am naming that I resolved that ambiguity toward
  the lab precedent rather than building a first-run wizard. A first-run
  wizard has a window where the service is deployed and unclaimed, which is
  worse.
- **CSRF: double-submit tokens on every state-changing admin route. This is
  where I deliberately diverge from the precedent.** files-hosting has no
  CSRF tokens at all and relies solely on `SameSite=Strict`. For its three
  routes on an image host that is a defensible call. Our state-changing
  routes include "enable actions on this target" and "mint an
  actions-capable API key". `SameSite` is a browser-behaviour control, not
  an application control, and it is the only thing standing between a
  logged-in admin visiting any page and a forged request that widens the
  action blast radius. The constitution's escalation list names "anything
  that widens the action blast radius"; relying on a single browser-side
  control for exactly that seems wrong to me, and tokens cost about 30
  lines.
- Frontend: Jinja2 templates plus a small vanilla JS file driving a JSON
  admin API, built with `createElement`/`textContent` rather than
  `innerHTML`. No npm, no bundler, no CDN. The audit log view is the only
  page with real interactivity (filter by key, target, tool, status; paginate
  server-side, because 1,113 alerts in a small lab suggests the audit log
  will not be small either).
- Container: digest-pinned `python:3.12-slim`, non-root with `APP_UID`/`APP_GID`
  build args matching the docker.int deploy account, bind mounts rather than
  named volumes for the credential store and audit log (a named volume
  silently gives you an empty local dir if the host mount vanished; a bind
  mount of a missing path fails loudly), healthcheck via python rather than
  curl against `127.0.0.1` rather than `localhost`. All four of those are
  lessons already paid for by files-hosting.

### Fork 5: skills are content in the image, indexed at build time, exposed three ways from one loader.

**Recommendation: `skills/<slug>/SKILL.md` with YAML frontmatter, a
build-time generated index, one loader feeding resources, prompts, and
tools.**

Layout:

```
skills/
  suite-api-auth/SKILL.md
  actions-howto/SKILL.md
  metrics-query-patterns/SKILL.md
  _index.json          generated at build time, committed
```

Frontmatter: `slug`, `title`, `version` (semver), `summary` (one line, this
is what `list_skills` returns), `tags`, `updated` (ISO date), and
`applies_to` (which target versions/adapter kinds it is valid for, which
matters because of fork 6).

One `skills/loader.py` parses frontmatter and body once at startup into an
in-memory index, and three surfaces read from it:

- **MCP resources**: `skill://<slug>`, `mimeType: text/markdown`, with the
  full body. `resources/list` returns slug + title + summary.
- **MCP prompts**: only a curated subset gets a prompt, the ones that are
  actually a task template rather than reference material. I would start
  with one: `run_action_safely`. Registering every skill as a prompt because
  we can is how prompt lists become unusable.
- **Tools**: `list_skills(tag=None)` returns **frontmatter only** (slug,
  title, summary, version, tags), never bodies. `get_skill(slug)` returns
  the full body. This is progressive disclosure, and it is the whole reason
  the tool path exists separately from the resource path: a tool-calling-only
  consumer like VCF Private AI Services cannot browse resources, so
  `list_skills` has to be cheap enough to call speculatively.

**Versioning: git is the version of record, frontmatter carries the
human-facing semver.** No separate version store, no runtime editing. A
`tools/validate-skills.py` in CI checks frontmatter parses, `slug` matches
the directory, `version` is semver, and body size is under a cap (I would
set 32 KB; a skill that does not fit is two skills).

**The important call: skills ship inside the image, not on a volume.** This
is a security property, not a packaging convenience. Skill content is
injected verbatim into the context of every consuming LLM, including VCF
Private AI Services, which means `skills/` is prompt-injection surface into
every client. Putting it on a writable volume makes that surface
runtime-mutable by anyone with volume access and invisible to review. Putting
it in the image makes every change a reviewed PR with a SHA. The
corresponding cost is honest and I will name it: updating a skill requires a
rebuild and redeploy, so Phase 3's mining round cannot hot-load its output.
I think that is the right trade for content that steers other models, and it
is not a close call.

**Phase 3 fits without changes.** The mining round produces new
`skills/<slug>/SKILL.md` files through normal PRs. Nothing about the loader,
the index, or the three surfaces changes as the corpus grows from 3 to 30.
The only thing I would add now against that future is the `tags` field and
the `tag=` filter on `list_skills`, because at 30 skills an unfiltered list
starts costing real context.

### Fork 6: pin to the 9.0 offline OpenAPI, probe version at registration, record drift in-repo. There is no live schema to introspect.

The assignment's preferred path is closed: **the 9.0.2 appliance does not
serve Swagger/OpenAPI.** I probed five plausible paths and got 404 on four;
the fifth (`/suite-api/internal/docs/swagger.json`) returns 403 without the
unsupported-API header and 404 with it. So runtime schema introspection is
not available and fork 6 has to be answered without it.

Second finding that shapes the answer: **the API version and the product
version are decoupled.** `/api/versions/current` returns
`releaseName: "VCF Operations 9.0.2.0"` alongside `major: 2, minor: 2`. The
"9.0.2" the lab talks about is the product release name; the suite-api's own
version number is 2.2. Any version-gating logic that pattern-matches "9.0"
against the API version field will silently never match. This is exactly the
kind of thing that would have cost an afternoon later.

**Recommendation, three parts:**

1. **`reference/docs/operations-api.json` (the 9.0 OpenAPI from
   vcf-content-factory) is the contract.** Not 9.1. We target the appliance
   we have. I would not vendor the file into this repo (it is 1.3 MB and the
   constitution says knowledge sources are read-only inputs); I would cite it
   by path and pin the endpoint shapes we depend on into our own code as
   typed models.

   The good news, and it lowers the stakes on this whole fork: the 9.0 to 9.1
   public surface is **purely additive**, 250 paths to 343, with **zero
   removed**, and the pagination defaults and `/api/resources` parameter list
   are byte-identical between the two specs. Building against 9.0 does not
   paint us into a corner. The two behavioural changes that would bite are
   not shape changes at all: 9.1 removes direct vCenter authentication (so
   `token/acquire` against a local or SSO source becomes the only path, which
   is what we do anyway), and 9.1 forces FIPS on with no way to disable it,
   which has already caused one real failure in this lab. Both are worth a
   line in the drift doc and neither changes the design.

   The bad news, and it is the reason part 2 exists: **the spec runs ahead of
   the implementation.** Several `/internal/*` paths that the internal
   OpenAPI documents return 404 on a live 9.0.2 appliance. So the OpenAPI is
   the contract for shapes, and the appliance is the authority on existence.
   Never trust a path because the spec has it.
2. **A capability probe at target registration, not at call time.** When a
   target is registered in the admin UI, the server does a small fixed set of
   cheap GETs (`/api/versions/current`, `/api/adapterkinds`, plus a
   1-row probe of each list endpoint we depend on), records the results in
   the target registry as a `capabilities` blob with a timestamp, and
   surfaces it in `list_targets`. Tools consult the stored blob. **Not
   per-call feature detection**, which doubles request volume and makes tool
   latency depend on appliance responsiveness for no benefit given targets
   change version approximately never. The admin UI gets a "re-probe" button
   for after an appliance upgrade, and the probe re-runs automatically if the
   stored `releaseName` stops matching what a call observes.
3. **Drift findings are committed, not remembered.** A
   `scripts/drift-probe.py` runnable by hand against devel, writing
   `docs/recon/drift-<releaseName>.md`. Run by hand and committed, **not run
   in CI**, because CI must never hold VCF credentials per the constitution
   and there is no way to give CI a live appliance without breaking that. So
   the drift check is a documented human-triggered step before a release,
   with its output in the repo. I would seed `docs/recon/drift-9.0.2.0.md`
   with everything in section 0 of this document.

The specific drift items I would record now: the `major/minor` decoupling;
no live Swagger; `/suite-api/internal/*` returns **HTML** on 403 and the
`Bearer` scheme returns **HTML** on 401, so the error path must not assume
`response.json()` succeeds (this is a real crash waiting to happen in a
naive client, and vcf-content-factory's `client.py` does not guard it
because it never hits those paths); `/api/reports/definitions` is a 400 and
the correct path is `/api/reportdefinitions`; that both `vRealizeOpsToken`
and `OpsToken` authenticate successfully with `OpsToken` being the canonical
9.x form; that the action id carries a literal space needing URL encoding;
that `GET /api/actions` is 404; and that several spec-documented
`/internal/*` paths do not exist on 9.0.2.

**One scope call I am making explicitly: MVP tools use the public
`/suite-api/api/*` surface only.** The `/internal/*` surface has genuinely
useful capabilities with no public equivalent (server-side view rendering via
`/internal/views/{id}/data/export` is the tempting one, and it would make a
great tool). But it requires `X-Ops-API-use-unsupported: true`, it is
explicitly unsupported by the vendor, its documented paths do not reliably
exist, and its drift between versions is the least predictable thing in this
API. Taking a dependency on it in the round that establishes the
architecture is borrowing risk against a capability nobody has asked for
yet. I would revisit it in Phase 3 as a deliberate, separately-argued
addition rather than let it in through the side door now.

---

## 2. Risks

**Where this breaks, including the ones that make my own proposal look worse.**

- **The 142 number is from a lab appliance, and it is the foundation of my
  fork-1 argument.** A production VCF Ops with more management packs
  installed will have more. That direction only strengthens the case against
  generation. But the *reverse* risk is real and I should name it: if a peer
  argues that 142 is small enough that generation is fine, my answer is not
  the count, it is the missing parameter metadata. I want that to be the load
  bearing argument precisely because it does not depend on the count.
- **I did not call `POST /api/actions/{id}/query` against devel.** It is
  documented as a populate/read operation and almost certainly does not
  mutate, but it is a POST against a live appliance and the assignment says
  read-only recon, so I chose the conservative reading and skipped it. The
  cost is that my `plan_action` design rests on the OpenAPI's documented
  response shape rather than an observed one, and I do not know the real
  token cost of a populated action response. **This is my one-hour, one-question
  item** (see below).
- **The `plan_id` design has a TOCTOU hole I have not closed.** Between
  `plan_action` and `apply_action`, the appliance state can change: the
  resource can be deleted, powered off, or migrated. The plan hash protects
  against the *client* altering the body, not against the *world* changing
  underneath it. Re-running the populate call inside `apply_action` and
  diffing would close it, at the cost of a second round trip and a new
  failure mode ("plan is stale, re-plan"). I lean toward doing the re-populate
  and treating a diff as a hard refusal, but I have not costed it and I would
  want the critique round to push on this. It is the weakest part of my
  action design.
- **Storing plans server-side is state I have otherwise avoided.** Plans
  need a TTL, eviction, and a size bound, or they are a memory leak and a
  place for stale credentials-adjacent data to sit. An alternative is a
  stateless signed plan token containing the whole body, which removes the
  storage but puts the execution body in the client's hands (signed, so it
  cannot be altered, but it can be replayed within the TTL). I picked
  server-side state; I am not certain it is right.
- **Two scopes may be too coarse and I have argued for coarseness on
  aesthetic grounds as much as safety grounds.** A peer could reasonably say
  that "actions on devel" versus "actions on devel, but only power
  operations" is a distinction Scott will want. My defence is the checked-in
  allowlist, but the allowlist is global rather than per-key, so a key with
  `actions` gets the whole allowlist. If that is wrong, the fix is
  per-key allowlist subsetting and it is not hard; I just do not think the
  complexity earns itself at MVP.
- **My fork-2 argument leans on a package inspection, not on having built
  anything.** I verified `streamable_http_app()` returns a Starlette app and
  that `TokenVerifier` is a one-method protocol. I have not verified that
  mounting the MCP app alongside a Starlette admin app in one process
  actually works cleanly, particularly around the session manager's
  lifespan, which `streamable_http_app()` sets up lazily. If the lifespan
  wiring fights a parent app's lifespan, "one listener" gets harder and part
  of my fork-4 argument for Starlette-over-Flask weakens. That is a half-hour
  spike and I did not spend it.
- **The reference SDK is version 1.28 and moving fast.** Fifty-plus releases
  are listed. Pinning exactly and upgrading deliberately is mandatory, and I
  should not pretend the reference SDK is stable just because it is
  first-party.
- **Skills-in-the-image blocks hot updates, and Phase 3 is the round that
  will most want them.** I called this trade deliberately, but if the mining
  round produces 30 skills that need iteration, "rebuild the container to fix
  a typo" will chafe, and someone will propose a volume. I would rather
  argue that out now than have it retrofitted under time pressure.
- **Projection can hide the field someone needed.** A 92% reduction is
  achieved by throwing away 92% of the bytes, and my claim that they were
  all waste is based on eyeballing one resource record plus the observation
  that 53% is HATEOAS links. The `fields=` escape hatch mitigates this, but
  only if the model knows to reach for it, which means the tool description
  has to say so.
- **Provenance: not everything above is my own measurement.** The numbers in
  section 0 are mine, measured against devel this round. A significant part
  of the API detail in the client-hardening and drift sections comes from
  vcf-content-factory's recon corpus, verified by that project against its
  own instances rather than by me against devel. Where the two disagree I
  should be trusted on devel-specific facts and it should be trusted on
  breadth. One visible disagreement: it records 2,742 resources where I
  measured 508, which I read as different instances rather than a
  contradiction, but I have not confirmed that and it is the sort of gap that
  hides a real misunderstanding.
- **I had the auth-scheme question backwards until I checked the vendor doc.**
  I reasoned from the shipping client and the appliance's 401 message that
  `vRealizeOpsToken` was canonical; the vendor documentation says the
  opposite. Both work, so nothing breaks, but it is a reminder that "the
  working code must be right" is a bad prior in a codebase carrying legacy
  forms, and I would rather my peers see me get that wrong here than inherit
  the conclusion from me silently.
- **I have not verified anything about what VCF Private AI Services actually
  tolerates.** My "14 tools is safe, 142 is a gamble" claim is reasoning from
  general LLM behaviour, not from a datasheet or a test. It is the least
  evidenced claim in the proposal and it is load-bearing for fork 1's
  framing (though not for its conclusion, which rests on the metadata
  problem).

**One hour and one question.** I would spend it running `POST /api/actions/{id}/query`
against devel for three representative actions (Power Off VM, Set CPU Count
and Memory for VM, and one APPOSUCP plugin config), with Scott's explicit
nod that a populate call counts as a read. The question: **what does a real
populated action response look like, how big is it, and does
`methodParameters` actually carry enough type information to build a useful
plan?** That single answer firms up `plan_action`'s entire design, tells me
the real token cost of the plan surface, and would be the last thing needed
to falsify my fork-1 recommendation if `methodParameters` turned out to be
richer and cheaper than I think.

---

## 3. Division-of-labor claim

**I would own the suite-api client, the projection layer, and the target
registry plus credential store (`ops/`, `registry/`).**

The reasoning is context rather than harness capability. I have spent this
round with hands on the live devel appliance and I now hold specific,
verified knowledge that is expensive to transfer and easy to get subtly
wrong from documentation: that error bodies are sometimes HTML and sometimes
JSON depending on which path you hit, that the resource payload is half
HATEOAS links, that `/api/reportdefinitions` is the path and
`/api/reports/definitions` is a 400, that pagination echoes `pageSize` back
so you can detect server-side caps, that the `major/minor` fields do not
mean what they look like. That is the knowledge the client and projection
layers are made of. Rebuilding it in another resident's head costs more than
the code is worth.

The credential store belongs with the client because the two are coupled
through the token lifecycle: the thing that decrypts a credential and the
thing that replays it on a 401 want to be designed together, and the AAD
scheme I proposed binds ciphertext to `target_id`, which is a registry
concept.

**What I think is better owned elsewhere.** The admin UI is not my strongest
claim. It is closely modelled on an existing lab service, and the resident
that can most faithfully port files-hosting's patterns (the hash-shape
guard, the uid pinning, the bind-mount-not-named-volume reasoning, the
Compose `$`-escaping) should take it, weighted toward whoever has the most
context on that repo and on the docker.int slot contract. If that is a peer,
it should be a peer; porting a known-good pattern rewards familiarity with
the original more than it rewards fresh design, and I would rather the
person who knows why `esc() { printf '%s' "${1//\$/\$\$}"; }` exists writes
the deploy script.

Similarly, the **skills surface** is the most separable piece in the whole
build. It touches nothing safety-critical, has no live-appliance dependency,
and its interface to the rest of the server is one loader module. It is the
right piece to hand to whichever resident is least loaded, and it should not
go to whoever owns `ops/` (me) because that would serialize two things that
have no reason to be serial.

The **action pipeline** I would rather not own alone, and not for capacity
reasons. It is the piece where the constitution's invariants actually bite,
and the no-self-review rule means whoever writes it cannot sign off on it.
Given that, I would slightly prefer the author of `apply_action` to be
someone other than the author of the client it calls through, so that the
peer reviewing the gate logic is not also the person who built the layer
underneath it. That is an argument for a peer taking `tools/actions.py` even
though I am proposing its design.

---

## 4. Rough estimate

Order of magnitude for the Phase 1 build (server skeleton, registry,
credential store, token lifecycle, read-only tool families verified against
devel, minimal admin UI, CI build and slot deploy):

**Roughly 3,000 to 4,000 lines of Python plus templates, across 3 to 5 working
sessions of the size this round was, spread over 2 to 3 rounds.** Broken down
by the rough shape:

- `ops/` client, token lifecycle, projection: ~600 lines, and the least
  risky, because `client.py` is a working reference for the hard parts.
- `registry/` plus credential store plus keyring rotation: ~500 lines, of
  which rotation is a third and is the part most likely to be under-tested.
- Read-only tool families (inventory, metrics, alerts, reports, targets):
  ~800 lines, mostly mechanical once projection exists.
- Admin UI (Starlette routes, Jinja2 templates, vanilla JS, hashpw CLI):
  ~900 lines including templates and CSS. files-hosting did a full CRUD UI
  in ~350 lines of frontend; ours has more screens.
- Skills surface: ~250 lines plus content.
- Tests with synthetic fixtures and a mock suite-api: ~800 lines, and I am
  deliberately estimating this as the second-largest item rather than an
  afterthought, because the constitution forbids live credentials in CI,
  which means the mock appliance is the *only* thing CI can test against and
  it therefore has to be good.
- CI and deploy: mostly ported from files-hosting, so small in lines and
  disproportionate in elapsed time.

**What blows this up, in descending order of likelihood:**

1. **The deploy handoff.** The assignment already says the lab-admin
   provisioning request is in flight. If the slot facts do not exist when
   Phase 1 is otherwise done, Gate 1 (connect Claude Code to the deployed
   URL) cannot be met, and the work sits finished-but-ungated. This is the
   most likely schedule risk and it is entirely outside the team's control.
2. **The mock suite-api.** If the fixtures are not faithful, every read-only
   tool passes CI and fails against devel, and we discover it one tool at a
   time. Getting the fixtures right early is worth more than it looks, and
   getting them wrong is the thing most likely to double the estimate.
3. **The one-listener assumption.** If mounting the MCP app inside a parent
   Starlette app has lifespan problems, the container grows a second process
   or an internal proxy, and the deploy story, healthcheck, and fleet-caddy
   conf all get more complicated.
4. **Rotation.** An online, interruptible key rotation is the kind of feature
   that is 100 lines and three days, because the failure modes are all
   partial-state. If the estimate is wrong anywhere in the credential store,
   it is here. I considered proposing rotation as Phase 2 to protect the
   estimate and decided against it, because a credential store shipped
   without a rotation path is one that never gets one.

I have not padded this. If it is wrong, I expect it is wrong low on tests
and low on the admin UI, which are the two places I have historically
underestimated.

---

## Asides

**No standing ruling re-litigated.** I have built on all of them: the
unofficial naming, the docker.int slot behind fleet-caddy, devel-first with
prod read-only later, Streamable HTTP with API keys, and post-deploy
admin-UI credential configuration. I do not disagree with any of them.

**No SPEC amendment proposed.** I went looking for a contract error in the
`Authorization: OpsToken` line and tested it against devel; both schemes
work, so there is no error. Everything else in the SPEC matched what I
observed. The one place I resolved an ambiguity rather than found an error is
SPEC 4.3's "bootstrap admin credential provisioned at first deploy", which I
read as the env-var-hash pattern rather than a first-run wizard, and I have
named that resolution in fork 4 rather than quietly assuming it.

**Recon hygiene.** All appliance access was GET against devel, guarded by an
in-script assertion on the hostname. Nothing was run against prod. No
credential value appears in this document, in any commit, or in any output I
produced. The recon scripts live in `/tmp` and are not part of this branch.

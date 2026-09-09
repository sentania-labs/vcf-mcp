# Recover console administrator access

Use this ceremony only when the console admin password is lost. It proves control of the container platform, not merely access to the web interface.

Recovery has these effects:

- The admin password is replaced during the next appliance startup.
- Every existing console session is invalidated on its next request.
- MCP API keys survive unchanged.
- Stored backend credentials and their encryption keyring are not exposed or changed.
- The console displays the recovery time until an admin acknowledges the notice.
- Recovery and notice dismissal are recorded in the durable configuration event ledger, shown under "Recent configuration audit" in the console's Audit tab. Dismissing the banner does not delete these records.

The recovery file is `/keys/admin_recovery_password`. It must be a regular file owned by UID 10001, mode `0600`, containing one UTF-8 line of at least 16 bytes with no trailing newline. The filename is deliberately different from `/keys/admin_bootstrap_password`. A leftover bootstrap mount cannot recover an initialized appliance.

The application reads the recovery file only at startup and removes it after validation, before hashing the password and beginning the database transaction. This consumes the file even if recovery fails later. If the database transaction fails, the prior password remains valid, but the operator must stage a new recovery file before restarting to retry recovery.

An empty, multiline, invalid UTF-8, oversized, wrongly owned, group-readable, or world-readable file is refused. If validation or file removal fails, the password hash and session generation remain unchanged. The health endpoint reports `admin_recovery` in `startup_errors`.

## Docker Compose

Run these commands from the directory containing the deployed Compose project. They stage the password without writing it to a host file or command history. Replace the service name only if the deployment renamed `vcf-mcp-web`.

```sh
docker compose stop vcf-mcp-web
read -r -s -p 'New admin password: ' VCF_MCP_RECOVERY_PASSWORD
printf '%s' "$VCF_MCP_RECOVERY_PASSWORD" | docker compose run --rm --no-deps -T \
  --entrypoint sh vcf-mcp-web \
  -c 'umask 077; cat > /keys/admin_recovery_password'
unset VCF_MCP_RECOVERY_PASSWORD
docker compose up -d vcf-mcp-web
docker compose ps vcf-mcp-web
```

Wait for the service to report healthy, then sign in with the new password. Confirm the recovery banner and its time. The file should no longer exist on the `/keys` volume.

## Kubernetes

Do not mount a Kubernetes Secret directly at the recovery path. Projected Secret volumes are read-only, so the application cannot consume the file. Instead, scale the appliance down and use a one-off Job to copy a temporary Secret into the existing writable keys PVC. The normal Deployment never receives cluster credentials.

First create the temporary Secret from terminal input, without a plaintext file:

```sh
read -r -s -p 'New admin password: ' VCF_MCP_RECOVERY_PASSWORD
printf '%s' "$VCF_MCP_RECOVERY_PASSWORD" | kubectl -n <namespace> create secret generic \
  vcf-mcp-admin-recovery --from-file=admin_recovery_password=/dev/stdin
unset VCF_MCP_RECOVERY_PASSWORD
kubectl -n <namespace> scale deployment/<deployment> --replicas=0
kubectl -n <namespace> wait --for=delete pod \
  -l '<deployment-selector>' --timeout=120s
```

Apply this one-off Job after substituting the exact deployed image and keys PVC name:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: vcf-mcp-stage-admin-recovery
  namespace: <namespace>
spec:
  ttlSecondsAfterFinished: 300
  template:
    spec:
      restartPolicy: Never
      securityContext:
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
      containers:
        - name: stage
          image: <exact-deployed-vcf-mcp-image>
          command:
            - sh
            - -c
            - install -m 0600 /recovery/admin_recovery_password /keys/admin_recovery_password
          volumeMounts:
            - name: keys
              mountPath: /keys
            - name: recovery
              mountPath: /recovery
              readOnly: true
      volumes:
        - name: keys
          persistentVolumeClaim:
            claimName: <keys-pvc>
        - name: recovery
          secret:
            secretName: vcf-mcp-admin-recovery
            defaultMode: 0440
```

Wait for the Job to complete, remove the temporary platform objects, then start the appliance:

```sh
kubectl -n <namespace> wait --for=condition=complete \
  job/vcf-mcp-stage-admin-recovery --timeout=120s
kubectl -n <namespace> delete job/vcf-mcp-stage-admin-recovery
kubectl -n <namespace> delete secret/vcf-mcp-admin-recovery
kubectl -n <namespace> scale deployment/<deployment> --replicas=1
kubectl -n <namespace> rollout status deployment/<deployment>
```

Sign in with the new password and confirm the recovery banner. If startup refuses the file, inspect pod logs and `/healthz`, correct the ceremony, and restart. Do not add the temporary Secret or Job to the standing workload definition.

# Pack registry round-trip authorization

This artifact preserves the principal's explicit authorization before the
outward-facing scratch publication used to prove the GHCR design.

> Confirm empirically that GHCR accepts a non-image OCI artifact and that a
> cosign signature over it verifies with certificate identity pinning intact.
> Use a throwaway artifact under a scratch name.

The scratch artifact is authorized only for this proof. It does not authorize
deletion, force-pushing, or publication of a release tag.

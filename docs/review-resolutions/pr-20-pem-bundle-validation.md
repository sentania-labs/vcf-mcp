# PR 20 PEM bundle validation follow-up

- **Finding:** Reject mixed PEM bundles before appliance CA persistence.
- **Resolution:** Every submitted PEM block must be a CA certificate. A private
  key or any other non-certificate block is rejected with its block type named.
- **Authority:** Firstmate directed this P1 external review correction. The
  Captain did not review or authorize this follow-up.

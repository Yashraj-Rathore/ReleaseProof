# ADR-012 — Runner Is a Separate Trust Boundary
**Status:** Accepted

Untrusted repository code never runs inside the Django/Celery/control-plane host. The runner accepts a narrow versioned execution plan and returns a narrow result. No Docker socket, cloud credentials, customer secrets, unrestricted network, or host mounts are exposed. The runner milestone begins with a threat review and sentinel tests.

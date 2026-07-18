# Security Policy

## Supported versions

TrainForge is an early-stage project. Security fixes are applied to the latest release and the current `main` branch.

| Version | Supported |
| --- | --- |
| Latest release | Yes |
| `main` | Yes |
| Older releases | No |

## Security boundary

TrainForge currently targets single-node and small-team deployments. The application does not provide built-in user authentication, tenant isolation, or fine-grained authorization. Production operators are responsible for placing it behind a controlled access layer that provides authentication, HTTPS, request limits, and appropriate network policy.

The API accepts files and can start resource-intensive processing. Do not expose the API container directly to an untrusted network. Publish the Web proxy only, restrict access at an external reverse proxy or gateway, and review upload and compute limits before deployment.

## Data handling

The source repository must never contain:

- SQLite databases, WAL/SHM files, SQL dumps, or other business data stores;
- source images, videos, annotations, dataset releases, training runs, or inference output;
- model weights or exported PT, ONNX, TensorRT, and similar artifacts;
- `.env` files, access tokens, passwords, API keys, private keys, or certificates;
- internal task definitions, server addresses, operational logs, or incident records.

Keep runtime data and models in persistent, access-controlled storage outside the source tree. Back up the database together with its corresponding data and model directories, encrypt backups where appropriate, verify integrity before restoration, and apply an explicit retention policy.

The screenshots in this repository must use synthetic or explicitly licensed data. They must not contain employee information, customer content, internal task names, private hostnames, IP addresses, credentials, or local user paths.

## Deployment guidance

- Keep `.env` only on the deployment host or in a protected secret store.
- Terminate TLS and enforce authentication before requests reach TrainForge.
- Restrict inbound traffic with a firewall, security group, VPN, or trusted gateway.
- Keep the API and its managed data directory writable only by the service account.
- Mount model directories with the minimum permissions required by the deployment.
- Review container memory, CPU, process, shared-memory, upload, and disk-space limits.
- Back up data before upgrades and test schema or path migrations against a copy.
- Avoid including sensitive paths, media, or payloads in issues and diagnostic logs.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability.

Use GitHub's private vulnerability reporting feature for this repository:

1. Open the repository's **Security** tab.
2. Choose **Report a vulnerability**.
3. Include the affected version, impact, reproduction steps, and a minimal sanitized proof of concept.

If private vulnerability reporting is unavailable, contact the maintainer through the private contact method listed in the GitHub profile. Do not attach business data, production credentials, or unredacted logs.

You can expect an initial acknowledgement within seven days. Disclosure timing will be coordinated after the issue is reproduced and a remediation path is available.

## Dependency and license considerations

TrainForge depends on third-party packages with their own security and licensing policies. Review [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md), enable Dependabot and GitHub secret scanning, and rebuild images regularly to receive upstream security fixes.


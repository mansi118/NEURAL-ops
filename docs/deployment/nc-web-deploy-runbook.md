# nc-web launch runbook — AWS-native

nc-web is a pure Matrix client (no backend). It is hosted **AWS-native and isolated from the matrix/spine
box** — we do NOT change how the spine is deployed. The client talks to the public Matrix homeserver
(`matrix.neuraledge.in`, itself on EC2); hosting the static app lives entirely in S3 + CloudFront.

## Live URL (primary)

**https://d1fpr59vpk40a3.cloudfront.net** — the branded NeuralChat client (chat + Decision Queue +
Fidelity). HTTPS via the CloudFront default cert; no registrar/DNS dependency.

Sign in with a seat account and chat with Aria / Recon. That is the MVP — branded product chat, needing
none of the gated backend deploys. The Decision Queue and Fidelity panels render empty until their
producer harnesses get live seams (see `technical-plan-3-month-2026-07.md`).

## AWS resources (ap-south-1 · acct 071126865245) — new, isolated, reversible

| Resource | Id | Note |
|---|---|---|
| S3 bucket | `neuralchat-web-071126865245` | private, default Block-Public-Access; holds the static build |
| CloudFront | `ESZ2GZFNY5Z8U` → `d1fpr59vpk40a3.cloudfront.net` | OAC to the bucket, SPA error routing, HTTPS default cert |
| OAC | `E18QDL446BAGGI` | CloudFront → S3 read |

Nothing on the matrix box (mdad / Synapse / Traefik) is touched by this. The nc-web container previously
placed on the box for testing is removed once this URL is confirmed live, so the spine returns to its
prior comfortable state.

## Redeploy a new build
```
./nc-web/deploy/aws-deploy.sh
```
Builds, syncs `dist/` to S3 (immutable assets, no-cache `index.html`), and invalidates CloudFront.

## Optional — a custom domain later
To serve at e.g. `chat.neuraledge.in`, add an ACM cert (us-east-1) for the name, attach it + the alias to
the distribution, and point DNS at the CloudFront domain. DNS for `neuraledge.in` is authoritative on
ns1/ns2.dns-parking.com (Hostinger), not Route53 — so that record is a registrar action. The
`*.cloudfront.net` URL above needs none of that.

## Rollback
Delete the CloudFront distribution + the S3 bucket (both isolated; no effect on any spine service).
nc-web holds no server state.

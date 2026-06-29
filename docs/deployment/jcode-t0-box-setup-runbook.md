# jcode T0 — Box Setup Run-Book (the one physical unblock)

**Dated 2026-06-29.** This is the document that precedes the [T0 spike run-book](./jcode-t0-spike-runbook.md):
how to stand up the **one box** that converts the entire built-and-tested adapter into something that has
actually run. Everything upstream of this is done (jcode adapter T1–T6, nc-channels, the T7 offline
red-team gate, the seat-adapter assembly + `python -m neop_jcode_adapter preflight`, all green on main).

## Honest framing (what this can and can't do)
- This is **Layer 2, step 1** of the remaining path (box → T0 → live T7 + M1b → first contact). It is the
  **only physical unblock** — not more code, not a date.
- A green T0 proves the wiring runs. It does **NOT** make the product "production-ready" — that's the
  Day-90-class evidence gate (fidelity over real seats + a clean-isolation window), which no box and no
  runbook can compress. See `path-to-day-90.md` / `go-live-checklist.md`.
- **The agent cannot execute this for you.** Provisioning a billable EC2 instance in the prod account is a
  procurement step; the agent has the AWS creds and can run the provisioning commands **on your explicit
  go**, but the jcode-binary build may need your GitHub access. This run-book makes the step zero-fumble.

---

## The premise correction (verified 2026-06-29, read-only, against the live account)
The recurring mental model — *"the EC2 m7i.2xlarge that runs the runtime can host Docker"* — **is false, and
that matters**, because a runbook pointed at a host that can't run Docker is a wish:

| Claim | Verified reality |
|---|---|
| "an m7i.2xlarge runs the runtime" | **No such instance exists.** The runtime is **ECS Fargate** (`infra/terraform/ecs.tf:68 launch_type="FARGATE"`). Fargate **cannot host a Docker daemon** for nested jail containers. |
| "use an existing EC2 box" | The account's EC2 instances (`customer-connect-backend`, `matrix-server`, `openclaw-bot`, …) are all `t3.*` in the **default VPC** (`172.31/16`) — unrelated workloads, none in the spine VPC, none sized for the jail. |
| "the palace is reachable from anywhere" | The palace is **VPC-internal** — `convex.neos-dogfood.local:3211` is a **Cloud Map private DNS name** that resolves only inside the spine VPC. |

⇒ **The T0 box must be provisioned NEW, inside the spine VPC.** The good news from the same trace: the spine
VPC has **public subnets + an Internet Gateway but no NAT** — so a box in a public subnet reaches the
**palace** (intra-VPC) *and* the **model host** (via the IGW) with **no NAT needed**, sidestepping the exact
EIP-quota wall that shaped the whole no-NAT spine.

## Verified facts (all real IDs — account 071126865245, ap-south-1)
| Thing | Value |
|---|---|
| Spine VPC | `vpc-0591a756a76205140` (`neos-dogfood-vpc`, `10.40.0.0/16`) |
| **Box subnet** (public, auto-assign public IP) | `subnet-032fec17fb749025c` (`neos-dogfood-public-0`, az `ap-south-1a`) |
| Internet egress (for the model host) | IGW `igw-00de658df7cd0e74e` — **no NAT** |
| Palace `/mcp` (intra-VPC only) | `http://convex.neos-dogfood.local:3211/mcp` |
| Test palaceId (neuraledge) | `k17f0b36y2f7h4sbr3pqp5wxg189cvg1` |
| Model key (the on-hand, unblocked path) | Secrets Manager `neos-dogfood/OPENROUTER_API_KEY` → provider `openrouter`, egress host `openrouter.ai` |

---

## Step 1 — provision the box (the agent CAN run this on your go)
A single instance; `m7i.2xlarge` (8 vCPU / 32 GB) is comfortable, `m7i.xlarge` is enough for a single-seat
spike. Amazon Linux 2023 (has `dnf`, SSM agent preinstalled). Place it in the public subnet with a public IP.

```bash
# SG: no inbound (use SSM Session Manager); egress 443 (model + GitHub) + intra-VPC to the palace.
SG=$(aws ec2 create-security-group --region ap-south-1 --group-name neop-t0-box \
  --description "jcode T0 spike box" --vpc-id vpc-0591a756a76205140 --query GroupId --output text)
aws ec2 authorize-security-group-egress --region ap-south-1 --group-id "$SG" \
  --ip-permissions IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges='[{CidrIp=0.0.0.0/0}]'
aws ec2 authorize-security-group-egress --region ap-south-1 --group-id "$SG" \
  --ip-permissions IpProtocol=tcp,FromPort=3211,ToPort=3211,IpRanges='[{CidrIp=10.40.0.0/16}]'

# Instance profile: SSM (no SSH keys) + read the model key secret. Reuse or create a role with
# AmazonSSMManagedInstanceCore + secretsmanager:GetSecretValue on neos-dogfood/OPENROUTER_API_KEY.

aws ec2 run-instances --region ap-south-1 \
  --image-id resolve:ssm:/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --instance-type m7i.2xlarge --subnet-id subnet-032fec17fb749025c --associate-public-ip-address \
  --security-group-ids "$SG" --iam-instance-profile Name=<t0-box-profile> \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=neop-t0-box}]'
```
Connect with **SSM** (no inbound port): `aws ssm start-session --target <instance-id> --region ap-south-1`.

## Step 2 — Docker (prereq #4)
```bash
sudo dnf install -y docker git && sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"   # re-login (or newgrp docker) so `docker info` works rootless-to-you
docker info >/dev/null && echo "docker OK"
```

## Step 3 — the jcode binary (prereq #1, the genuinely hard procurement step)
jcode = `1jehuang/jcode`@`master` (public; Rust). **Configured, never forked** (CLAUDE.md). Build on the box
(same arch as the seat image):
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y && . "$HOME/.cargo/env"
git clone https://github.com/1jehuang/jcode && (cd jcode && cargo build --release)
sudo install jcode/target/release/jcode /usr/local/bin/jcode && jcode --version
```
*(If the clone needs auth, that's the one spot that may want your GitHub access — the only step the agent
can't necessarily complete headless.)*

## Step 4 — the adapter + the model key (prereq #2)
```bash
git clone https://github.com/mansi118/NEURAL-ops && cd NEURAL-ops && pip install -e .   # pure-stdlib + optional cryptography
# Pull the model key from Secrets Manager into the env. NEVER echo it; it rides the env, never config/argv.
export OPENROUTER_API_KEY="$(aws secretsmanager get-secret-value --region ap-south-1 \
  --secret-id neos-dogfood/OPENROUTER_API_KEY --query SecretString --output text)"
```

## Step 5 — the go/no-go check (this is the done-bar of THIS run-book)
Set the seat env and run the preflight built for exactly this moment. It names any remaining gap and exits
0 only when the box is ready:
```bash
export PALACE_ID=k17f0b36y2f7h4sbr3pqp5wxg189cvg1
export NEOP_ID=t0_spike                          # NEVER blank/_admin/_system → the shim refuses those
export NEOP_SEAT_CLASS=A                          # A+jail for the round-trip (palace auto-allow)
export PALACE_MCP_URL=http://convex.neos-dogfood.local:3211/mcp
export NEOP_PROVIDER=openrouter
export NEOP_IMAGE=neos-jcode:latest              # the seat image (built on the box)
export NEOP_WORKDIR=/var/seats/$PALACE_ID/$NEOP_ID && mkdir -p "$NEOP_WORKDIR"
export JCODE_HOME=$NEOP_WORKDIR/.jcode
export NEOP_JAIL_ENFORCED=1

python -m neop_jcode_adapter preflight
#   → "preflight: READY"  (exit 0)  ⇒ the box is go for T0.
#   → any "fail:" line names exactly what's still missing.
```

## Step 6 — run T0
With preflight green, follow **[`jcode-t0-spike-runbook.md`](./jcode-t0-spike-runbook.md)** Phase A→D
(render seat → build jail → `jcode run "remember <fact>; then search <fact>"` round-trips through the shim
to the palace → a row lands in Convex under the test scope; the safety gate fires for a Class B seat).
**T0 is STOP-and-show** — show the result, do not proceed to T9/M1b without sign-off.

## Teardown + cost
A spike is **hours, not months**. `m7i.2xlarge` ≈ $0.45/hr on-demand (ap-south-1). When done:
`aws ec2 terminate-instances --region ap-south-1 --instance-ids <id>` (and delete the SG). Nothing here
touches the live Fargate spine — the box is additive and disposable.

## What this run-book does NOT do (so the framing stays honest)
It opens the door; it does not declare the room clean. After T0: **live T7** (does the running container
actually enforce egress + lockdown — the security gate before any real data), then **M1b** (a NEop doing
real, gated work), then **nc-channels live** (first contact via Element). And then the part no document
shortcuts — fidelity + the clean-isolation window over real usage. Refs: `go-live-checklist.md`.

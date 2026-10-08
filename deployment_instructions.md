# Student Lab Guide: Automated Full-Stack Deployment via DoIT GitLab & GCP

This guide walks you through claiming your free Google Cloud Platform (GCP) credit, provisioning a Linux VM, and wiring up a GitLab CI/CD pipeline that deploys automatically whenever a merge request lands on `production`.

**The deploy model:** you keep developing on `main` (and feature branches) exactly as before. `production` is a separate, protected branch that nobody can push to directly — the only way code reaches it is a merge request from `main`. Merging that request is what triggers the deploy pipeline. This means the live site only ever reflects code that went through review, and "who/what deployed this" is always answered by "whoever approved that merge request."

**Do Part 1 as soon as this project is released, not the night of your deploy deadline.** Claiming your credit takes a few minutes; the technical setup in Parts 2–7 takes real, first-time-doing-it hours and is worth spreading out.

**Get your first successful deploy done days before the deadline, not on deadline night.** Every team's pipelines run on the same shared course runner. In the last day or two before the deadline that runner is at its busiest: jobs wait in a queue, and builds are more likely to fail for reasons that have nothing to do with your code. Once one deploy has worked end to end, every later deploy is only an update, and a slow or failed pipeline costs you a retry instead of your deployment. A first deploy also tends to fail a few times before it works, so leave room for that. Part 9 covers how to read a failed pipeline and retry it.

---

## Part 1: Claim Your Credit & Create Your GCP Project

> **Redeem your credit in the first week of the project.** Nothing else in this guide can start until the \$50 credit is in your billing account: without it you cannot create the VM. The steps below take a few minutes when they go smoothly, but they depend on two emails from Google, and a coupon problem has to go from you to your instructor to Google, which can take days. Finding that out the week of the deadline leaves no time to deploy.

1. Open the **[Student Coupon Retrieval Link](https://vector.my.salesforce-sites.com/GCPEDU?cid=GLily0ISk7KS8BZu2MF9jzDkW4ljFlV5DIAH1RHbTEj5cLdnkAlACYggtXugb7Vv/)**. Enter your name and your **`@wisc.edu`** email address; the address must be your school one. You can request only one coupon per email address. No separate email with this link will be sent to you: this is where it lives.
2. Google sends a confirmation email to that `@wisc.edu` address. Open it and confirm your details. Google then sends a second email containing your **coupon code**. Check your spam folder if either email has not arrived after a few minutes.
3. Redeem the code: follow the redeem link in the coupon email (or go to [console.cloud.google.com/edu](https://console.cloud.google.com/edu)), sign in with a Google Account, enter the coupon code, and accept. This creates a Cloud Billing account for the course with your \$50 credit applied — you don't need to create a project first.
   - The coupon is tied to the email address it was sent to, not to the account you redeem it with. If Google Cloud refuses your `@wisc.edu` Google account, sign in with a personal Google Account and redeem the code there.
   - Use that same Google Account for every later step in this guide.
4. Log into the [Google Cloud Console](https://console.cloud.google.com/). In the top toolbar, click the project dropdown and click **New Project**. Name it `qna-<your-netid>` and click **Create**. On the **Billing** page for the project, make sure it's linked to the course's education billing account from step 3.
5. **Deadlines:** you must request and redeem your coupon by **January 2, 2027**, and the credit can be spent through **September 2, 2027**. Do steps 1–3 this week anyway: they depend on Google's emails arriving, which you don't control.
6. **This one credit is your budget for the rest of the course.** The same \$50 has to cover this project's VM, Project 4's Vertex AI (Gemini) API calls, and — if you choose a deployed or LLM-backed idea — your Final Project. It is not topped up later, and when it runs out Google stops your resources. Plan your spending with the numbers in the next section.

### What the VM costs, and a budget that works

These are approximate prices for the VM this guide has you create (Part 2). Check the **Billing** page for your real figures.

| State of the VM | What you pay for | Approximate cost |
|---|---|---|
| **Running** | The machine, its disk and its static IP | \$0.15 an hour, about \$3.50 a day |
| **Stopped** | The disk and the reserved static IP only | About \$0.50 a day |
| **Deleted, IP released** | Nothing | \$0 |

So \$50 buys roughly 330 hours of a running VM and nothing else. A VM left running for the whole project would use the entire credit in about two weeks. A plan that fits:

| When | VM state | Approximate cost |
|---|---|---|
| Setting up and testing your deployment (about 40 hours in total, spread over the project) | Running only while you work | \$6 |
| All the other days of the project (about three weeks) | Stopped | \$10 |
| The grading window: from the evening of the due date until your grading report is posted, plus any late days you use | Running without a break | \$3.50 a day, about \$10–15 |
| After grading (Part 10) | Deleted | \$0 |

That leaves about \$20 for Project 4 and the Final Project. To stay on this plan:

- **Stop the VM every time you finish working** (Part 8, last step). This is the single biggest saving.
- **A team needs only one VM.** Host it in one member's Google Cloud project. The other member's credit is then untouched by this project.
- **Set a budget alert.** In the console, open **Billing** → **Budgets & alerts** → **Create budget**, set the amount to \$50, and keep the alerts at 50% and 90%. An alert only sends you an email; it does not stop anything.
- **Look at Billing → Reports once a week.** It shows what each day cost. A stopped VM that still costs several dollars a day means something else is running.
- **In Project 4,** prefer the cheap default model and the repo's keyless mock mode while developing.

---

## Part 2: Provision Your Virtual Machine (Google Compute Engine)

### 1. Launch the Server
1. In the left navigation menu of the GCP Console, go to **Compute Engine** → **VM Instances** (click **Enable** if asked to enable the Compute Engine API). Click **Create Instance**.
2. Configure your server:
   * **Name:** `production-web-server`
   * **Region:** `us-central1` (Iowa) — **Zone:** `us-central1-a`
   * **Machine Configuration:** **General-purpose** → **E2 series** → **`e2-standard-4`** (4 vCPU, 16 GB RAM) — smaller types can't run the finished stack (Ollama, Infinity, ChromaDB). It costs about \$0.14/hour while running (~\$100/month if left on).
   * **Boot Disk:** Click **Change**. Switch the OS to **Ubuntu 24.04 LTS** and set the size to **50 GB**.
   * **Data protection:** under **Backups**, select **No backups**. The default snapshot schedule snapshots the disk every day, and those snapshots keep costing money even after the VM is deleted.
3. Under **Firewall**, check both **Allow HTTP traffic** and **Allow HTTPS traffic**.
4. Under **Security**, set **Service accounts** to **No service account**, then open **Manage access** and check **Control VM access through IAM permissions** (this turns on OS Login, which you and your deploy job use to sign in).
5. Click **Create**.

### 2. Lock in a Static Public IP
By default, GCP's external IPs are ephemeral and change whenever the VM is stopped and started. Reserve a static one so your grading URL never moves.
1. In the GCP search bar, search for **VPC Network** → **IP Addresses**.
2. Find the ephemeral external IP tied to `production-web-server`.
3. Click the three-dot menu on its row → **Promote to static IP address**. Name it `permanent-grading-ip`.

### 3. Install Docker
With OS Login there are no SSH keys to manage: you sign in with your Google account, and your deploy job with the Google identity you set up in Part 5.

1. In the VM instances list, click **SSH** on your VM's row to open a terminal on it.
2. Install Docker Engine and the Compose plugin:
   ```bash
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER
   ```
   Log out and back in for the group change to take effect, then confirm with `docker compose version`.
3. Still on the VM, in your home directory, generate one matching JWT key pair. Keep the two printed lines for the next step:
   ```bash
   openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out jwt.pem
   echo "JWT_PRIVATE_KEY=$(base64 -w0 jwt.pem)"
   echo "JWT_PUBLIC_KEY=$(openssl pkey -in jwt.pem -pubout | base64 -w0)"
   rm jwt.pem
   ```
4. Create an app directory and a production `.env` file (this file is **never** committed to git or passed through CI — you type production secrets directly on the VM, once):
   ```bash
   sudo mkdir -p /srv/app && cd /srv/app
   sudo nano .env   # paste the contents of .env.template, then change the lines below
   ```
   Change these lines and leave the rest as in `.env.template`:
   * `MYSQL_ROOT_PASSWORD`, `MYSQL_PASSWORD`, `ADMIN_PASSWORD` — new, strong values using only letters and digits (they don't need to match your local dev `.env`).
   * `DATABASE_URL` — replace `change_me_app` with the same value as `MYSQL_PASSWORD`, or the backend can't reach the database.
   * `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` — the two lines printed in step 3.
   * `OAUTH2_PROXY_SHARED_SECRET` — leave it empty.
   * `GRADER_PASSWORD_HASH` — copy it exactly as it is in `.env.template`. Your application creates an admin account named `grader` from it, which course staff use to grade your deployment (see T9). If this line is missing or altered, grading cannot sign in.

   MySQL applies these passwords only the first time it starts with an empty database; changing them later means wiping its volume.

---

## Part 3: The `production` Branch

Course staff have already created and protected a `production` branch in your repository, so no one can push to it directly.

1. Leave `main` as the repository's **default branch** — day-to-day development still targets `main`. `production` only ever moves via a merge request from `main`.
2. To deploy: open a merge request from `main` into `production`, get it reviewed, and merge it. That merge is what the CI/CD pipeline in Part 6 watches for.
3. When merging a `main` → `production` merge request, use the **Merge Commit** method (GitLab's default) — don't squash. Grading verifies this branch's protection by walking its commit history, and a squash merge rewrites commits into new SHAs that no longer look like they came from `main`, which reads as a direct push even though it wasn't one.

---

## Part 4: Set Up the GitLab Container Registry

Your CI pipeline needs somewhere to publish the Docker images it builds, and your VM needs to be able to pull them back down. Rather than standing up a second cloud identity system, use the **Container Registry that's already built into your GitLab project** on `git.doit.wisc.edu`.

1. Your CI jobs push using GitLab's own predefined variables (`CI_REGISTRY`, `CI_REGISTRY_IMAGE`, `CI_REGISTRY_USER`, `CI_REGISTRY_PASSWORD`) — nothing to configure for that side.
2. Your VM, however, is *outside* GitLab CI, so it needs a credential to pull images. There is none to create: the deploy job (Part 6) signs the VM in with the job's own `CI_REGISTRY_PASSWORD`, which stops working as soon as the job ends.

---

## Part 5: Let CI Sign In to Google Cloud Without Secrets

Every CI job can get a short-lived ID token from GitLab that says which project and branch it runs for. Here you tell Google Cloud to accept those tokens — only from your project's `production` branch — in exchange for a service account that may sign in to your VM. The deploy stage therefore needs no credentials at all, so there is nothing to store as a CI/CD variable for T9's secrets requirement.

Below, `<your-repo-path>` is your repo's path on `git.doit.wisc.edu`, such as `cdis/cs/courses/aicoding/fa26/student-repos/p3/<your-repo>`.

Do **one** of the two options below — they create exactly the same setup. Option A clicks through the console; Option B pastes one script into Cloud Shell.

### Option A: Google Cloud console

1. Open each of these and click **Enable** where it's offered (some may already be enabled): [Identity and Access Management (IAM) API](https://console.cloud.google.com/apis/library/iam.googleapis.com), [IAM Service Account Credentials API](https://console.cloud.google.com/apis/library/iamcredentials.googleapis.com), [Security Token Service API](https://console.cloud.google.com/apis/library/sts.googleapis.com), [Cloud Identity-Aware Proxy API](https://console.cloud.google.com/apis/library/iap.googleapis.com), [Cloud OS Login API](https://console.cloud.google.com/apis/library/oslogin.googleapis.com).
2. Go to **IAM & Admin** → **Workload Identity Federation** → **Get started**:
   * **Create an identity pool** — **Name:** `gitlab`. **Continue**.
   * **Add a provider to pool** — **Select a provider:** **OpenID Connect (OIDC)**; **Provider name:** `gitlab`; **Issuer (URL):** `https://git.doit.wisc.edu/`; **Audiences:** **Allowed audiences**, **Audience 1:** `https://git.doit.wisc.edu`. **Continue**.
   * **Configure provider attributes** — **Google 1** `google.subject` ← **OIDC 1** `assertion.project_id + ":" + assertion.ref`; **Add mapping**: **Google 2** `attribute.project_path` ← **OIDC 2** `assertion.project_path`. Under **Attribute conditions**, **Add condition**, and enter this as the **Condition CEL**:
     ```
     assertion.project_path == '<your-repo-path>' && assertion.ref == 'production' && assertion.ref_protected == 'true'
     ```
     **Save**.
3. Go to **IAM & Admin** → **Service Accounts** → **Create service account**. **Service account name:** `gitlab-deployer` → **Create and continue**. Under **Permissions**, use **Select a role** and **Add another role** to add **Compute OS Admin Login**, **IAP-secured Tunnel User** and **Compute Viewer**, then click **Done**.
4. Back in **Workload Identity Federation**, open the `gitlab` pool → **Grant access** → **Grant access using service account impersonation**. **Service account:** `gitlab-deployer`; under **Select principals**, **Attribute name:** `project_path`, **Attribute value:** `<your-repo-path>`. **Save**, then click **Dismiss** on the **Configure your application** dialog — you don't need its file, so leave its **Provider** field empty.
5. On the pool's page, the **IAM principal** starts with `principal://iam.googleapis.com/projects/<PROJECT_NUMBER>/…`. Note that number and your **Project ID** (copy it from the project picker — it can differ from the project name) for Part 6.

### Option B: Cloud Shell

In **Cloud Shell** (the `>_` icon at the top of the GCP Console), set your two values. Replace both placeholders before pressing Enter, and copy the exact **Project ID** from the project picker — it can differ from the project name:

```bash
PROJECT_ID=<your-project-id>
GITLAB_PROJECT=<your-repo-path>
```

Then run this block as is. It stops at the first error:

```bash
( set -e
: "${PROJECT_ID:?}" "${GITLAB_PROJECT:?}"
gcloud config set project $PROJECT_ID
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')

# APIs for token exchange, SSH through Google's IAP proxy, and OS Login
gcloud services enable iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com iap.googleapis.com oslogin.googleapis.com

# Accept ID tokens from git.doit.wisc.edu, but only from your repo's protected production branch
gcloud iam workload-identity-pools create gitlab --location=global
gcloud iam workload-identity-pools providers create-oidc gitlab --location=global --workload-identity-pool=gitlab \
  --issuer-uri=https://git.doit.wisc.edu/ --allowed-audiences=https://git.doit.wisc.edu \
  --attribute-mapping='google.subject=assertion.project_id + ":" + assertion.ref,attribute.project_path=assertion.project_path' \
  --attribute-condition="assertion.project_path == '$GITLAB_PROJECT' && assertion.ref == 'production' && assertion.ref_protected == 'true'"

# The identity your deploy job becomes: it may sign in to your VM as an admin, through IAP
gcloud iam service-accounts create gitlab-deployer
# A brand-new service account can take a minute to become usable, so retry each grant
retry() { for i in 1 2 3 4 5 6 7 8 9 10 11 12; do "$@" && return; echo "Not ready yet, retrying in 10s..."; sleep 10; done; return 1; }
for ROLE in compute.osAdminLogin iap.tunnelResourceAccessor compute.viewer; do
  retry gcloud projects add-iam-policy-binding $PROJECT_ID --role=roles/$ROLE --condition=None --format=none \
    --member=serviceAccount:gitlab-deployer@$PROJECT_ID.iam.gserviceaccount.com
done
retry gcloud iam service-accounts add-iam-policy-binding gitlab-deployer@$PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/iam.workloadIdentityUser --format=none \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/gitlab/attribute.project_path/$GITLAB_PROJECT"

echo "Paste these into the deploy job's variables (Part 6):"
echo "    CLOUDSDK_CORE_PROJECT: $PROJECT_ID"
echo "    WIF_PROVIDER: projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/gitlab/providers/gitlab"
echo "    DEPLOY_SA: gitlab-deployer@$PROJECT_ID.iam.gserviceaccount.com"
)
```

If it stops partway, fix the cause and run only the commands after the one that failed — running the whole block again fails on the resources it already created.

The attribute condition is what ties deploy access to the branch-protection model in Part 3: a token from `main`, a feature branch, or any other project is rejected, so only a merge into `production` can deploy.

---

## Part 6: Add Build & Deploy Stages to `.gitlab-ci.yml`

Your repo already has a `.gitlab-ci.yml` with `lint`, `test`, and `secret-detection` stages that run on merge requests. **Add** `build` and `deploy` stages to it rather than replacing the file — both sets of jobs should coexist.

1. Add `build` and `deploy` to the existing top-level `stages:` list.
2. Append these jobs:

```yaml
build_and_push:
  stage: build
  # mirror.gcr.io is Google's public mirror of Docker Hub. Every team's jobs run on the
  # same course runner, and Docker Hub limits anonymous pulls per IP address, so pulling
  # from the mirror keeps a busy deadline night from failing with "toomanyrequests".
  image: mirror.gcr.io/library/docker:27.5-cli
  services:
    - name: mirror.gcr.io/library/docker:27.5-dind
      alias: docker
      # Also send the FROM lines in your Dockerfiles to the mirror first
      command: ["--registry-mirror=https://mirror.gcr.io"]
  variables:
    DOCKER_HOST: "tcp://docker:2375"
    DOCKER_TLS_CERTDIR: ""
  rules:
    - if: $CI_COMMIT_BRANCH == "production"
  script:
    - echo "$CI_REGISTRY_PASSWORD" | docker login "$CI_REGISTRY" -u "$CI_REGISTRY_USER" --password-stdin

    - docker build -f nginx/Dockerfile -t "$CI_REGISTRY_IMAGE/nginx:$CI_COMMIT_SHORT_SHA" .
    - docker push "$CI_REGISTRY_IMAGE/nginx:$CI_COMMIT_SHORT_SHA"

    - docker build -t "$CI_REGISTRY_IMAGE/backend:$CI_COMMIT_SHORT_SHA" ./backend
    - docker push "$CI_REGISTRY_IMAGE/backend:$CI_COMMIT_SHORT_SHA"

deploy_full_stack:
  stage: deploy
  image: gcr.io/google.com/cloudsdktool/google-cloud-cli:slim
  rules:
    - if: $CI_COMMIT_BRANCH == "production"
  needs:
    - build_and_push
  id_tokens:
    GITLAB_OIDC_TOKEN:
      aud: https://git.doit.wisc.edu
  variables:
    # From Part 5 — none of these are secrets
    CLOUDSDK_CORE_PROJECT: <PROJECT_ID>
    WIF_PROVIDER: projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/gitlab/providers/gitlab
    DEPLOY_SA: gitlab-deployer@<PROJECT_ID>.iam.gserviceaccount.com
  before_script:
    - echo "$GITLAB_OIDC_TOKEN" > .oidc_token
    - gcloud iam workload-identity-pools create-cred-config "$WIF_PROVIDER" --service-account="$DEPLOY_SA" --credential-source-file=.oidc_token --output-file=.gcp_creds.json
    - gcloud auth login --cred-file=.gcp_creds.json
  script:
    # docker-compose.prod.yml (Part 7) references the two images above by tag — copy it and the tag to the VM
    - gcloud compute scp docker-compose.prod.yml production-web-server:docker-compose.yml --zone us-central1-a --tunnel-through-iap --quiet
    - >
      echo "$CI_REGISTRY_PASSWORD" | gcloud compute ssh production-web-server --zone us-central1-a --tunnel-through-iap --quiet --command "
      sudo mv docker-compose.yml /srv/app/ &&
      sudo docker login $CI_REGISTRY -u $CI_REGISTRY_USER --password-stdin &&
      sudo CI_REGISTRY_IMAGE=$CI_REGISTRY_IMAGE IMAGE_TAG=$CI_COMMIT_SHORT_SHA sh -c 'cd /srv/app && docker compose pull && docker compose up -d --remove-orphans' &&
      sudo docker logout $CI_REGISTRY &&
      sudo docker image prune -af"
```

Both jobs are gated with `rules: if: $CI_COMMIT_BRANCH == "production"` — they simply don't run on any other branch, which is the second enforcement point (alongside the Workload Identity condition in Part 5) that keeps deploys tied to reviewed code on `production`.

**Keep the `mirror.gcr.io` image names and the `--registry-mirror` line as written.** If a build still fails with `toomanyrequests`, wait a few minutes and retry the job, and tell course staff.

**No shared runner picking up your pipeline?** If jobs sit "pending" indefinitely instead of running, your project's GitLab group may not have a runner available — ask course staff rather than assuming your YAML is wrong.

---

## Part 7: Add a Production Compose File

Your existing `docker-compose.yml` is for local development — it builds images from source, bind-mounts `./backend` for hot reload, and runs the backend with `--reload`. None of that belongs on the VM: the VM should run the **immutable images CI just built and pushed**, not rebuild from source or live-reload.

Create `docker-compose.prod.yml` at the repo root, based on your dev file, with the key differences:
- `nginx` and `backend` use `image: ${CI_REGISTRY_IMAGE}/nginx:${IMAGE_TAG}` / `image: ${CI_REGISTRY_IMAGE}/backend:${IMAGE_TAG}` instead of `build:` — the deploy job (Part 6) exports both variables before running `docker compose pull`, so `docker compose` substitutes them from the shell environment.
- No source bind-mounts, no `--reload`. The backend's `command` runs migrations first — `sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"` — or on a fresh database it waits forever for a schema.
- `backend` sets `APP_ENV=production`, not `development` — in development mode anyone can sign in as any NetID without a password.
- Only `nginx`'s port 80 is published — `mysql` and `redis` stay internal to the compose network (nothing external needs to reach them directly).
- `mysql`/`redis` still use named volumes so data survives a redeploy.

**Your RAG services belong in this file too.** The four services above are only what the starter ships. Once T5 is built, your application also needs Ollama, Infinity and ChromaDB on the VM, so add them to `docker-compose.prod.yml` the same way you added them to your dev file, with these production rules:
- **Give each one a named volume for its data:** ChromaDB's collections, Ollama's downloaded models, and Infinity's model cache. Without a volume, a redeploy that recreates the container erases what you ingested for T6 and downloads several gigabytes of models again.
- **Publish none of their ports.** The backend reaches them over the compose network; nothing on the internet should reach Ollama, Infinity or ChromaDB directly.
- **Use fixed public images** (`image:`), not `build:`, unless you add a matching build-and-push step to `build_and_push` in Part 6.
- **Mind the memory.** The VM has 16 GB. Infinity holds every embedding model you serve in memory at once (the 1.5B-parameter model from T6 is by far the largest), and Ollama loads the generation model on top of that. If the backend or a model server is killed or answers time out, check memory first (Part 9).

The `MYSQL_ROOT_PASSWORD`, `MYSQL_PASSWORD`, and other secrets referenced by this file come from the `.env` you created directly on the VM in Part 2 — `docker compose` reads a `.env` file in its working directory automatically, so nothing secret needs to pass through this file, CI, or git.

Merge `docker-compose.prod.yml` and your `.gitlab-ci.yml` changes into `main` through a merge request — `main` doesn't accept direct pushes. They reach `production` the same way any other change does, through the `main` → `production` merge request.

---

## Part 8: Run and Verify Your Deployment

1. Merge your `main` → `production` merge request (Part 3, step 2).
2. On `git.doit.wisc.edu`, open **Build** → **Pipelines** and confirm `build_and_push` and `deploy_full_stack` both run and succeed. Pipelines on any other branch should show these two jobs skipped, not failed.
3. Run `curl http://<YOUR_STATIC_IP>/api/health` and expect `{"status":"ok"}`. Then visit `http://<YOUR_STATIC_IP>/student/` (and `/staff/`, `/admin/`) and confirm each page loads. In production the NetID dev login is off: the student and staff login pages still show a **Dev Login** box, but it is rejected. The admin account (and accounts it creates) sign in with a password.
4. On the VM, run `sudo docker logs $(sudo docker ps -q --filter name=backend) 2>&1 | grep grader` and expect a `grader_account_ready` line (it is logged when the account is created, so look after your first deploy). That confirms the course grader account exists. You cannot test its password yourself; only course staff know it.
5. **Prepare the deployment for T6.** Grading re-runs your comparison against this deployment, not against your laptop, so everything the comparison needs must exist here:
   1. Pull every generation model named in your `eval/configs.json` into the VM's Ollama. On the VM, find the container with `sudo docker ps`, then run `sudo docker exec <ollama-container> ollama pull <model>` once per model. Confirm with `sudo docker exec <ollama-container> ollama list`.
   2. Sign in to the deployed staff app and ingest `eval/sample_data/` under every ingestion profile your `eval/configs.json` names, exactly as you did locally (T6, step 1). What you ingested on your own machine is not on the VM.
   3. From your own machine, run the harness against the deployment:
      ```bash
      HARNESS_BASE_URL=http://<YOUR_STATIC_IP> HARNESS_ADMIN_PASSWORD='<the ADMIN_PASSWORD from the VM .env>' \
          python eval/compare_harness.py
      ```
      Every question should complete without an HTTP error. Commit the `eval/report.json` and `eval/report.md` this run writes: a report produced by the deployment is the one grading can reproduce.
   4. After any redeploy, check that the models and the ingested profiles are still there (`ollama list`, and one question through the staff app). If they are gone, a volume is missing in `docker-compose.prod.yml`.
6. Record the URL in `DEPLOYMENT_URL.txt` at the repo root and merge it into `main` through a merge request, as instructed in `instructions.md` (T9).
7. Stop the VM (**Compute Engine** → **VM instances** → **⋮** → **Stop**) whenever you finish working, and start it again before your next deploy. **Have it running whenever a grading run should count:** each run tests your live deployment at that moment, so the VM must be up on the night of the due date, and on the night of any late day you use (see T9). A stopped VM scores no deployment credit for that run. A stopped VM still costs about \$0.50 a day for its disk and static IP (see the budget in Part 1); only Part 10 brings the cost to zero.

---

## Part 9: When the Pipeline Fails or Stalls

### Watch the pipeline

1. On `git.doit.wisc.edu`, open your repository, then **Build** → **Pipelines**. The newest pipeline is at the top. A pipeline for the `production` branch appears a few seconds after you merge into it.
2. Click the pipeline to see its jobs. Each job shows a status:
   - **pending** — waiting for the shared runner to become free. Nothing is wrong yet.
   - **running** — click the job to watch its log live.
   - **passed** or **failed** — click the job to read the full log.
3. In a failed job's log, scroll to the bottom. The last command printed (the line starting with `$`) and the lines after it are the failure.

### Retry a job

Open the failed job and click **Retry** (top right of the job page). A retry runs the same commit again, so you do not need a new merge request. Retry `build_and_push` first if it failed; `deploy_full_stack` runs after it automatically.

Retry once or twice for the load-related failures in the table below. Do not retry over and over, and do not push empty commits to restart the pipeline: every extra run joins the same queue and slows it down for everyone, including you.

### Is it the shared runner, or is it your project?

All teams share one runner and one path to the image registries, so some failures come from load. This is how to tell them apart:

- **It is probably load** if the error is about pulling an image, the network, a timeout, or the runner itself, or if the same commit passes when you retry it.
- **It is probably your project** if the error names one of your files or commands, and it fails at the same step in the same way on a retry. Reproduce it on your own machine with the same command the job ran (for example `docker build -t test ./backend`).

| What you see | Likely cause | What to do |
|---|---|---|
| Job stays **pending** for a long time | The shared runner is busy with other teams' jobs | Wait. Do not cancel and restart: you lose your place in the queue. If it has been pending for more than an hour, tell course staff |
| `toomanyrequests` while pulling an image | A registry is rate-limiting the runner | Wait a few minutes, then retry the job. Check that you kept the `mirror.gcr.io` image names and the `--registry-mirror` line from Part 6 |
| `Cannot connect to the Docker daemon at tcp://docker:2375` | The Docker service for the job did not start in time | Retry the job. If it happens every time, compare your `build_and_push` job with Part 6 line by line |
| `runner system failure`, or the job is cut off partway with no error from your commands | A problem on the runner | Retry the job |
| An error from `npm`, `tsc`, `pip` or a `COPY` step during `docker build` | Your code or Dockerfile does not build | Not load. Fix it locally, then merge the fix through `main` into `production` |
| `deploy_full_stack` fails at `gcloud auth login`, or with a permission error | The sign-in from Part 5 does not match this job | Check that the job ran on `production`, that `<your-repo-path>` in Part 5 is exactly your repository's path, and that the three variables in the job match Part 5. New permissions can take a few minutes to take effect, so retry once |
| `deploy_full_stack` fails at `gcloud compute scp` or `gcloud compute ssh` | The VM is stopped, or its name or zone differs from the job | Start the VM, check the name and zone in the job, then retry |
| The deploy job passes but `/api/health` does not answer | A container failed to start on the VM | SSH to the VM and run `sudo docker ps -a`, then `sudo docker logs <container>` for any container that is not `Up` |
| Questions time out, a `502`/`504` comes back from `/api/`, or a container keeps restarting after it worked before | The VM ran out of memory, or an answer took longer than the web server waits | On the VM, run `free -h` and `sudo docker stats --no-stream`. Serve fewer or smaller models at once. Check that you kept the `proxy_read_timeout` line in `nginx/nginx.prod.conf` |
| The harness or the staff app reports an unknown model or an empty result on the deployment, but it works locally | The model was never pulled on the VM, or the content was never ingested there | Redo Part 8, step 5 |
| `no space left on device` on the VM | Old images or model files filled the disk | On the VM, run `sudo docker system df` to see what is using space |

### When to ask course staff

Ask when a job has been pending for more than an hour, or when a load-type failure keeps happening after two retries spaced a few minutes apart. Send the link to the failed job, not a screenshot of part of the log.

---

## Part 10: After Grading — Delete the VM and Release the IP

A stopped VM keeps charging for its disk and its static IP, about \$15 a month, until you delete them. Left alone until December, that is credit you needed for Project 4 and the Final Project.

**When:** after your TA code review (T11) is finished and your Project 3 grade is final. Until then, keep the VM (stopped is fine): your TA may ask you to start it for the review, and a regrade may need it.

1. **Delete the VM.** **Compute Engine** → **VM instances** → select `production-web-server` → **Delete**. Its boot disk is deleted with it.
2. **Release the static IP.** Deleting the VM does not do this, and a reserved IP that is not attached to anything costs more than one in use. **VPC Network** → **IP addresses** → select `permanent-grading-ip` → **Release static address**.
3. **Check for leftovers.** Under **Compute Engine**, open **Disks** and **Snapshots**. Both lists should be empty. Delete anything that remains.
4. **Do not close your billing account or remove the credit.** Project 4 and the Final Project use the same credit.
5. **Confirm two days later.** **Billing** → **Reports** should show no new Compute Engine cost for this project.

Your repository, its `production` branch and your images in the GitLab Container Registry stay as they are; they cost you nothing.

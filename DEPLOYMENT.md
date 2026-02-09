# BowlingMate Deployment Guide

## GCP Project Setup (from scratch)

When setting up a **new** GCP project for Cloud Run deployment via GitHub Actions, follow this exact sequence. Skipping steps will cause permission errors that take 30+ minutes each to debug.

### 1. Create Project
- Go to https://console.cloud.google.com/projectcreate
- Note the **Project ID** (auto-generated, e.g. `analog-reef-486909-s0`)
- Note the **Project Number** (e.g. `229166553554`)

### 2. Enable APIs (ALL of these, upfront)
```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  storage.googleapis.com \
  generativelanguage.googleapis.com \
  --project <PROJECT_ID>
```

### 3. Create Artifact Registry Repository (BEFORE first deploy)
Cloud Run's `--source` deploy needs this repo to exist. The SA may not have permission to auto-create it on first deploy due to IAM propagation delay.
```bash
gcloud artifacts repositories create cloud-run-source-deploy \
  --repository-format=docker \
  --location=us-central1 \
  --project=<PROJECT_ID>
```

### 4. Create GCS Bucket
```bash
gcloud storage buckets create gs://bowlingmate-clips \
  --location=us-central1 \
  --project=<PROJECT_ID>
```

### 5. Create Service Account with ALL Required Roles
```bash
# Create SA
gcloud iam service-accounts create bowlingmate-backend \
  --display-name="BowlingMate Backend" \
  --project <PROJECT_ID>

SA=bowlingmate-backend@<PROJECT_ID>.iam.gserviceaccount.com

# Grant ALL roles (do not skip any)
for ROLE in \
  roles/run.admin \
  roles/cloudbuild.builds.editor \
  roles/cloudbuild.builds.builder \
  roles/storage.admin \
  roles/iam.serviceAccountUser \
  roles/artifactregistry.admin \
  roles/serviceusage.serviceUsageConsumer \
  roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding <PROJECT_ID> \
    --member="serviceAccount:$SA" --role="$ROLE" --quiet
done
```

### 6. Grant Default Compute SA Permissions
Cloud Build uses the default compute service account. It also needs permissions:
```bash
COMPUTE_SA=<PROJECT_NUMBER>-compute@developer.gserviceaccount.com
CLOUDBUILD_SA=<PROJECT_NUMBER>@cloudbuild.gserviceaccount.com

for ROLE in \
  roles/serviceusage.serviceUsageConsumer \
  roles/logging.logWriter \
  roles/artifactregistry.writer \
  roles/storage.objectViewer; do
  gcloud projects add-iam-policy-binding <PROJECT_ID> \
    --member="serviceAccount:$COMPUTE_SA" --role="$ROLE" --quiet
done

# Cloud Build SA also needs serviceUsageConsumer
gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member="serviceAccount:$CLOUDBUILD_SA" \
  --role="roles/serviceusage.serviceUsageConsumer" --quiet
```

### 7. Create SA Key and Set GitHub Secrets
```bash
gcloud iam service-accounts keys create /tmp/sa-key.json \
  --iam-account=bowlingmate-backend@<PROJECT_ID>.iam.gserviceaccount.com

# Set via gh CLI
gh secret set GCP_SA_KEY --repo <GITHUB_USER>/<REPO> < /tmp/sa-key.json
rm /tmp/sa-key.json

# Also set the Gemini API key
gh secret set GOOGLE_API_KEY --repo <GITHUB_USER>/<REPO>
```

### 8. Get Gemini API Key
- Go to https://aistudio.google.com/apikey
- Create key for the new project
- Set as `GOOGLE_API_KEY` GitHub secret

### 9. Deploy
Trigger via GitHub Actions or manually:
```bash
gh workflow run deploy-backend.yml --repo <GITHUB_USER>/<REPO> --ref main
```

First build takes **~30-40 minutes** (MediaPipe compilation). Subsequent builds ~8 min with Docker layer cache.

---

## Hurdles & Lessons Learned

### 1. Service Account in Wrong Project
**Symptom**: `PERMISSION_DENIED: Permission 'run.services.get' denied`
**Cause**: SA key was from old project, not the new one
**Fix**: Always verify SA email ends with `@<NEW_PROJECT_ID>.iam.gserviceaccount.com`

### 2. APIs Not Enabled
**Symptom**: `Cloud Run Admin API has not been used in project`
**Cause**: APIs must be enabled before first deploy
**Fix**: Enable ALL APIs upfront (step 2)

### 3. Artifact Registry Repository Doesn't Exist
**Symptom**: `Permission 'artifactregistry.repositories.create' denied`
**Cause**: IAM propagation delay — SA has the role but GCP hasn't propagated it yet
**Fix**: Pre-create the `cloud-run-source-deploy` repo manually (step 3)

### 4. Default Service Account Missing Permissions
**Symptom**: `Build failed because the default service account is missing required IAM permissions`
**Cause**: Cloud Build uses the default compute SA, which needs its own roles
**Fix**: Grant roles to BOTH the deploy SA AND the default compute/Cloud Build SAs (step 6)

### 5. Environment Variables Override Code Defaults
**Symptom**: Feature toggles (MOCK_SCOUT, etc.) don't work despite code changes
**Cause**: `--set-env-vars` in deploy workflow is the source of truth, overrides config.py defaults
**Fix**: Always check `.github/workflows/deploy-backend.yml` for env var overrides

### 6. IAM Propagation Delay
**Symptom**: Permission denied even after granting role
**Cause**: IAM changes can take 1-5 minutes to propagate
**Fix**: Wait 2-3 minutes before retrying, or pre-create resources manually

---

## Current Configuration

| Setting | Value |
|---------|-------|
| GCP Project ID | `analog-reef-486909-s0` |
| GCP Project Number | `229166553554` |
| Cloud Run Service | `bowlingmate` |
| Region | `us-central1` |
| GCS Bucket | `bowlingmate-clips` |
| Service Account | `bowlingmate-backend@analog-reef-486909-s0.iam.gserviceaccount.com` |
| Cloud Run URL | `https://bowlingmate-m4xzkste5q-uc.a.run.app` |
| GitHub Repo | `kanarupandev/bowlingMate` |

## GitHub Secrets Required

| Secret | Description |
|--------|-------------|
| `GCP_SA_KEY` | Full JSON key for `bowlingmate-backend` service account |
| `GOOGLE_API_KEY` | Gemini API key for the project |

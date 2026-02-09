#!/bin/bash
# Deploy wellBowled Backend to Google Cloud Run
cd "$(dirname "$0")"

APP_NAME="wellbowled"
REGION="us-central1"
PROJECT_ID=$(gcloud config get-value project)

echo "🚀 Deploying $APP_NAME to Cloud Run ($REGION)..."

# Ensure API is enabled
# gcloud services enable run.googleapis.com

# Deploy Command
# --source . builds the Dockerfile in Cloud Build automatically
# --allow-unauthenticated because we handle security via X-WellBowled-Secret middleware
gcloud run deploy $APP_NAME \
    --source . \
    --region $REGION \
    --project $PROJECT_ID \
    --allow-unauthenticated \
    --set-env-vars="GOOGLE_API_KEY=${GOOGLE_API_KEY},API_SECRET=wellbowled-hackathon-secret,GCS_BUCKET_NAME=wellbowled-clips,GEMINI_MODEL_NAME=gemini-3-pro-preview,ANALYSIS_TIMEOUT=500" \
    --min-instances=1 \
    --port 8080

echo "✅ Deployment Triggered!"

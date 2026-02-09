#!/bin/bash
# Deploy BowlingMate Backend to Google Cloud Run
cd "$(dirname "$0")"

APP_NAME="bowlingmate"
REGION="us-central1"
PROJECT_ID="analog-reef-486909-s0"

echo "Deploying $APP_NAME to Cloud Run ($REGION)..."

# Deploy Command
# --source . builds the Dockerfile in Cloud Build automatically
# --allow-unauthenticated because we handle security via Bearer token middleware
gcloud run deploy $APP_NAME \
    --source . \
    --region $REGION \
    --project $PROJECT_ID \
    --allow-unauthenticated \
    --set-env-vars="GOOGLE_API_KEY=${GOOGLE_API_KEY},API_SECRET=bowlingmate-hackathon-secret,GCS_BUCKET_NAME=bowlingmate-clips,GEMINI_MODEL_NAME=gemini-3-pro-preview,ANALYSIS_TIMEOUT=500,ENABLE_OVERLAY=true,MOCK_SCOUT=false,MOCK_COACH=false" \
    --min-instances=1 \
    --memory=2Gi \
    --cpu=2 \
    --timeout=300 \
    --port 8080

echo "Deployment Triggered!"

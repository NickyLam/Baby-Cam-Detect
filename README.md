# Baby-Cam-Detect

Baby-Cam-Detect is an early backend MVP for baby safety monitoring from home
camera video streams. The current implementation focuses on two high-risk
safety alerts:

- baby appears to be sleeping face-down
- blanket or soft object appears to cover the baby's nose and mouth

This project is not a medical device and must not be treated as a substitute
for caregiver supervision.

## Current architecture

```text
RTSP camera stream
  -> FFmpeg frame extraction
  -> rolling frame buffer
  -> sampled vision-model analysis
  -> multi-frame confirmation
  -> event persistence
  -> clip/thumbnail upload
  -> Expo push notification
```

The backend is implemented with FastAPI, PostgreSQL, SQLAlchemy/Alembic,
FFmpeg, and pluggable vision LLM providers.

## Supported camera input

The current MVP accepts an RTSP URL. Many consumer cameras, including Xiaomi,
360, and TP-Link models, differ by firmware, region, cloud-account behavior,
and whether local RTSP/ONVIF access is enabled. This repository does not yet
include brand-specific discovery or setup flows.

Before adding a camera, verify that the device exposes a reachable local RTSP
stream. Future work should add camera connection profiles, ONVIF discovery,
snapshot previews, and actionable connection diagnostics.

Use `POST /api/v1/cameras/probe` to validate a candidate RTSP source before
storing it. The probe endpoint currently performs safety validation and URL
redaction; it does not yet open the stream or capture a snapshot.

## Backend setup

1. Create `backend/.env` with the required secrets:

   ```env
   SECRET_KEY=replace-with-a-long-random-secret
   DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/babycam
   REDIS_URL=redis://redis:6379/0
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=replace-me
   AWS_ACCESS_KEY_ID=replace-me
   AWS_SECRET_ACCESS_KEY=replace-me
   S3_BUCKET_NAME=replace-me
   ```

2. Start local dependencies and backend:

   ```bash
   docker-compose up --build
   ```

3. Apply database migrations from inside the backend environment:

   ```bash
   alembic upgrade head
   ```

4. Run tests locally:

   ```bash
   cd backend
   python -m pytest -q
   ```

## Privacy and safety notes

- RTSP credentials are stored server-side because the backend needs them to
  connect to cameras. API responses redact the RTSP URL and must not expose the
  full credential-bearing stream URL.
- Use a private object-storage bucket for event clips and thumbnails. Public
  clip URLs are not appropriate for home baby-monitoring video. Uploaded media
  is returned through short-lived signed URLs.
- Restrict CORS and disable debug/reload mode before any real deployment. The
  backend refuses to start with `DEBUG=false` while the default development
  `SECRET_KEY` is still configured.
- Treat LLM output as probabilistic. Product decisions must be validated with
  real representative video samples before relying on alerts.

## Implemented hardening foundations

- Per-camera multi-frame confirmation state is retained across sampled frames.
- Per-camera frame analysis is serialized to avoid unbounded concurrent LLM
  requests.
- RTSP sources are validated before storage and must target private LAN IPs.
- Camera API responses return `rtsp_url_redacted` instead of the stored RTSP
  credential-bearing URL.
- Alembic has an initial schema migration.
- A JSONL-based detection evaluation harness is available for labelled samples.
- Event media upload returns signed URLs instead of public S3 URLs.

## Remaining roadmap

1. Add real labelled video/frame datasets for normal sleep, face-down posture,
   blanket obstruction, empty crib, night vision, blur, and caregiver occlusion.
2. Add real stream-open snapshot probing behind the existing `CameraConnector`
   interface.
3. Move event notification dispatch to a durable outbox with Expo receipt
   handling and retry state.
4. Add mobile/frontend flows for camera setup, live status, alert review,
   dismiss/confirm feedback, and clip playback.
5. Add brand-specific camera setup guidance and ONVIF discovery where supported.

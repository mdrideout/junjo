# Deployment Guide

## Required Architecture: Same-Domain Deployment

⚠️ **IMPORTANT**: The backend API and frontend MUST be deployed on subdomains of the same domain.

### Why This is Required

This application uses session cookies with `SameSite=Strict` for security:
- **Prevents CSRF attacks** - Cookies are never sent in cross-site requests
- **Protects against session hijacking** - Cookies encrypted (AES-256) + signed (HMAC)
- **Ensures cookies only sent to your domain** - No third-party cookie access

### Correct Setup ✅

**Any combination on the same domain works:**

```
Option 1: Subdomain + Subdomain
Frontend:  https://app.example.com
Backend:   https://api.example.com

Option 2: Apex + Subdomain
Frontend:  https://example.com
Backend:   https://api.example.com

Option 3: Subdomain + Apex
Frontend:  https://app.example.com
Backend:   https://example.com
```

All share the same **registrable domain** (`example.com`) - **cookies work automatically**

The browser recognizes these as the same site because they share the same registrable domain (eTLD+1), so session cookies with `SameSite=Strict` are sent with all requests.

### Incorrect Setup ❌

```
Frontend:  https://app.example.com
Backend:   https://your-service-xyz.run.app
```

Different domains (`example.com` vs `run.app`) - **authentication will NOT work**

The browser will block all cookies because requests from `app.example.com` to `your-service-xyz.run.app` are considered cross-site.

---

## Platform Setup Examples

### Google Cloud Run

**Steps:**

1. **Deploy backend to Cloud Run**
   ```bash
   cd backend
   gcloud run deploy junjo-backend \
     --source . \
     --platform managed \
     --region us-central1 \
     --allow-unauthenticated
   ```

2. **Map custom domain to Cloud Run service**
   ```bash
   gcloud run domain-mappings create \
     --service junjo-backend \
     --domain api.example.com \
     --region us-central1
   ```

3. **Update DNS records**
   - Add CNAME record: `api.example.com` → `ghs.googlehosted.com`
   - Google Cloud Run will provision SSL certificate automatically

4. **Deploy frontend** (e.g., to Firebase Hosting, Vercel, Netlify)
   - Configure custom domain: `app.example.com`

5. **Configure backend environment variables**
   ```bash
   gcloud run services update junjo-backend \
     --update-env-vars CORS_ORIGINS=https://app.example.com \
     --update-env-vars JUNJO_ENV=production \
     --region us-central1
   ```

### AWS

**Backend on ECS/App Runner:**

1. Deploy container to ECS or App Runner
2. Configure Application Load Balancer with custom domain `api.example.com`
3. Set up SSL certificate via AWS Certificate Manager
4. Configure environment variables:
   ```bash
   JUNJO_ENV=production
   CORS_ORIGINS=https://app.example.com
   JUNJO_SESSION_SECRET=<your-secret>
   JUNJO_SECURE_COOKIE_KEY=<your-key>
   ```

**Frontend on Amplify/S3+CloudFront:**

1. Deploy frontend static assets
2. Configure custom domain: `app.example.com`
3. CloudFront will handle SSL automatically

### Docker Compose (Development)

Frontend and backend both run on `localhost` - **works out of the box!**

```yaml
# docker-compose.yml
services:
  backend:
    build: ./backend
    ports:
      - "1324:1324"
    environment:
      - JUNJO_ENV=development
      - CORS_ORIGINS=http://localhost:5151

  frontend:
    build: ./frontend
    ports:
      - "5151:5151"
```

In development, `localhost` is the same origin for both services.

---

## Environment Configuration

### Production Example

```bash
# .env
JUNJO_ENV=production                      # Enables https_only on cookies
CORS_ORIGINS=https://app.example.com     # Must match frontend domain(s)
JUNJO_SESSION_SECRET=<base64-encoded-secret>
JUNJO_SECURE_COOKIE_KEY=<base64-encoded-key>

# Database
DB_SQLITE_PATH=./data/production.db

# Ports
PORT=1323
```

### Generate Secrets

```bash
# Generate session secret (32 bytes)
openssl rand -base64 32

# Generate secure cookie key (32 bytes)
openssl rand -base64 32
```

### Multiple Frontend Domains

If you have multiple frontends (e.g., admin panel + main app):

```bash
CORS_ORIGINS=https://app.example.com,https://admin.example.com
```

All frontends must be on subdomains of the same domain (`example.com`).

---

## Security Features

This application implements multiple layers of security for session cookies:

### Cookie Attributes

- ✅ **Encrypted** - AES-256 encryption via `starlette-securecookies`
- ✅ **Signed** - HMAC signature prevents tampering
- ✅ **SameSite=Strict** - Prevents CSRF attacks
- ✅ **HttpOnly** - Prevents XSS cookie theft (JavaScript cannot read cookie)
- ✅ **Secure** - HTTPS-only in production (prevents transmission over HTTP)
- ✅ **30-day session lifetime** - Automatic expiration

### Middleware Stack (Order Matters)

```python
# Outer layer: Encryption
SecureCookiesMiddleware
  ↓ Encrypts/decrypts session cookie with AES-256

# Inner layer: Signing & Session Management
SessionMiddleware
  ↓ Signs/validates with HMAC, manages session state
```

This defense-in-depth approach ensures:
1. **Confidentiality** - Session data is encrypted (can't be read)
2. **Integrity** - Session data is signed (can't be modified)
3. **Authenticity** - Only server with secrets can create valid sessions

---

## Machine-to-Machine Authentication

For OTLP ingestion clients (OpenTelemetry SDKs), use **API Keys** instead of session cookies.

### Why API Keys for Machine Clients?

- ✅ **No browser required** - Works with any HTTP client
- ✅ **No cookie restrictions** - Not affected by SameSite policies
- ✅ **Long-lived credentials** - No 30-day expiration
- ✅ **Per-application isolation** - Different key for each service

### Setup

1. **Generate API key via web UI**
   - Sign in to `https://app.example.com`
   - Navigate to Settings → API Keys
   - Click "Create API Key"
   - Copy the 64-character key (shown only once)

2. **Configure OpenTelemetry SDK**
   ```python
   # Python example
   from opentelemetry import trace
   from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
   from opentelemetry.sdk.trace import TracerProvider
   from opentelemetry.sdk.trace.export import BatchSpanProcessor

   # Configure OTLP exporter with API key
   exporter = OTLPSpanExporter(
       endpoint="https://api.example.com:50051",  # gRPC endpoint
       headers=(
           ("x-api-key", "your-64-char-api-key-here"),
       ),
   )

   # Set up tracer
   trace.set_tracer_provider(TracerProvider())
   trace.get_tracer_provider().add_span_processor(
       BatchSpanProcessor(exporter)
   )
   ```

3. **API key works across any domain**
   - No SameSite restrictions
   - No CORS issues
   - Works from any network

---

## Troubleshooting

### Authentication Not Working

**Symptom**: User can't sign in, or is immediately signed out.

**Causes:**

1. **Cross-domain deployment** (most common)
   - ✅ Check: Are frontend and backend on subdomains of the same domain?
   - ❌ Example: `app.example.com` → `service.run.app` will NOT work
   - ✅ Fix: Map both to same domain (e.g., `api.example.com`)

2. **CORS misconfiguration**
   - ✅ Check: Does `CORS_ORIGINS` include your frontend URL?
   - ❌ Example: Frontend is `https://app.example.com` but `CORS_ORIGINS=http://localhost:5151`
   - ✅ Fix: Update `CORS_ORIGINS=https://app.example.com`

3. **HTTP in production**
   - ✅ Check: Is frontend accessed via HTTPS?
   - ❌ Example: Accessing `http://app.example.com` (no SSL)
   - ✅ Fix: Ensure SSL certificate is configured, redirect HTTP to HTTPS

4. **Browser privacy settings**
   - ✅ Check: Does browser block third-party cookies?
   - ✅ Fix: Use same-domain deployment (cookies are first-party)

### CORS Errors

**Symptom**: Browser console shows CORS errors.

```
Access to fetch at 'https://api.example.com/sign-in' from origin
'https://app.example.com' has been blocked by CORS policy
```

**Fix:**

```bash
# Backend .env
CORS_ORIGINS=https://app.example.com
```

Ensure:
- Protocol matches (`https://` not `http://`)
- No trailing slash on domain
- Exact match (wildcards not supported for credentials)

### Session Expires Too Quickly

**Symptom**: User is signed out after refreshing page.

**Causes:**

1. **Session cookie not persisting**
   - Check browser DevTools → Application → Cookies
   - Should see cookie named `session` with 30-day expiry

2. **Browser in incognito/private mode**
   - Session cookies may be deleted when browser closes
   - Expected behavior for privacy mode

---

## Advanced Configuration

### Custom Session Lifetime

To change the 30-day default:

```python
# backend/app/main.py
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_cookie.session_secret,
    max_age=86400 * 7,  # 7 days instead of 30
    https_only=is_production,
    same_site="strict",
)
```

### Local Development with Custom Domain

To test same-domain behavior locally:

1. **Edit `/etc/hosts`**
   ```
   127.0.0.1  app.local.test
   127.0.0.1  api.local.test
   ```

2. **Update backend CORS**
   ```bash
   CORS_ORIGINS=http://app.local.test:5151
   ```

3. **Access via custom domains**
   - Frontend: `http://app.local.test:5151`
   - Backend: `http://api.local.test:1324`

---

## Summary

✅ **DO:**
- Deploy frontend and backend on subdomains of the same domain
- Use HTTPS in production
- Configure `CORS_ORIGINS` to match your frontend domain
- Generate strong secrets for production
- Use API keys for machine-to-machine authentication

❌ **DON'T:**
- Deploy backend and frontend on different top-level domains
- Use wildcard CORS origins (`*`) in production
- Commit secrets to version control
- Use session cookies for non-browser clients

**Need help?** Check the logs on startup - the application validates configuration and provides helpful error messages.

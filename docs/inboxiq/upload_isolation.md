# Upload isolation and external asset pinning

Purpose: keep untrusted files and third-party assets from executing in the main app origin.

## Upload isolation (S3 + CloudFront + Route53)
- **Bucket**: create an S3 bucket just for uploads (e.g., `kalevent-uploads`), block public ACLs, allow only via a CloudFront origin access control/identity.
- **Headers on objects**: set `Content-Type` correctly, always set `Content-Disposition: attachment; filename="<name>"`, and set `X-Content-Type-Options: nosniff`. (Add a CSP like `default-src 'none'; sandbox;` if serving HTML must be blocked.)
- **CloudFront**: front the bucket; cache policy should forward only what’s needed and include the response headers above (response headers policy).
- **DNS**: add an A record Alias in Route53 for `files.kalevent.com` → the CloudFront distribution (not a CNAME). This keeps uploads on a separate origin from `kalevent.com`.
- **App config placeholders** (to wire later): `UPLOADS_BUCKET=kalevent-uploads`, `UPLOADS_HOST=https://files.kalevent.com`. Application code should generate links pointing to `UPLOADS_HOST` and never proxy uploads through the main app domain.
- **App helper**: `src/uploads.py` provides `upload_bytes(key, data, content_type, content_disposition)` and `build_public_url(key)` using the env vars above; it expects `boto3` at runtime.

## External asset pinning
- Current external script: `https://js.stripe.com/v3/` (Stripe-managed; SRI pinning not recommended because Stripe rotates files). All other assets are local (`/static`).
- Rule of thumb: if adding CDN assets, either self-host them under `/static` or include Subresource Integrity (`integrity` + `crossorigin="anonymous"`) with a pinned version. Keep a list of external assets in this doc when new ones are added.

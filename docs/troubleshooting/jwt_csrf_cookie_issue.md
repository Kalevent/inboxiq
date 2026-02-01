# JWT Cookie and CSRF Troubleshooting Guide

## Issue: Form Submissions Redirect to Login

### Symptoms
- User can view authenticated pages (GET requests work)
- Clicking form submit buttons redirects to login page
- Logs show "Missing CSRF token" errors
- No POST requests reach the Flask routes

### Root Cause Analysis

#### 1. JWT Cookie SameSite Configuration
**Problem**: `JWT_COOKIE_SAMESITE=None` in production environment

When `SameSite=None` is set:
- Cookies are intended for cross-site requests
- Browsers have strict requirements for sending these cookies
- Same-site form POST submissions may not include the cookies
- This causes JWT authentication to fail on form submissions

**Fix**: Use `JWT_COOKIE_SAMESITE=Lax` for production
- `Lax` allows cookies to be sent with top-level navigation (including form POSTs)
- `Lax` is appropriate for same-site applications
- `None` should only be used for true cross-site scenarios

#### 2. CSRF Token Validation
**Problem**: Flask-JWT-Extended CSRF protection enabled but token not properly passed

When `JWT_COOKIE_CSRF_PROTECT=True`:
- Flask-JWT-Extended expects CSRF token in form data
- Token must match the `csrf_access_token` cookie value
- Field name must be exactly `csrf_token`
- If missing or mismatched, request is rejected before reaching route handlers

**Implementation Requirements**:
```python
# In route handler (GET):
csrf_token_value = request.cookies.get("csrf_access_token") or request.cookies.get("csrf_refresh_token") or ""
return render_template("template.html", csrf_token_value=csrf_token_value)
```

```html
<!-- In template form: -->
<form method="POST">
  <input type="hidden" name="csrf_token" value="{{ csrf_token_value }}" />
  <!-- other form fields -->
</form>
```

### Configuration Reference

#### Development Environment
```ini
JWT_COOKIE_SECURE=False          # Allow HTTP for localhost
JWT_COOKIE_SAMESITE=Lax           # Best for same-site forms
JWT_COOKIE_CSRF_PROTECT=False     # Can disable for local dev convenience
```

#### Production Environment
```ini
JWT_COOKIE_SECURE=True            # Require HTTPS
JWT_COOKIE_SAMESITE=Lax           # Allow same-site form submissions
JWT_COOKIE_CSRF_PROTECT=True      # Enable CSRF protection
```

#### When to Use `SameSite=None`
- Cross-origin iframe embedding
- CORS requests from different domains
- Cross-site form submissions

**Warning**: `SameSite=None` requires `Secure=True` (HTTPS only)

### Debugging Steps

1. **Check if cookies are being sent**:
```python
# In login_required decorator:
current_app.logger.warning({
    "event": "auth.page_redirect",
    "reason": str(exc),
    "path": request.path,
    "cookies": list(request.cookies.keys()),
})
```

Look for: `access_token_cookie`, `csrf_access_token` in the cookies list

2. **Check environment variables in pod**:
```bash
kubectl exec -n kaley POD_NAME -- python3 -c "import os; print('JWT_COOKIE_CSRF_PROTECT:', os.getenv('JWT_COOKIE_CSRF_PROTECT')); print('JWT_COOKIE_SAMESITE:', os.getenv('JWT_COOKIE_SAMESITE'))"
```

3. **Verify secret is properly loaded**:
```bash
kubectl get secret inboxiq-env -n kaley -o jsonpath='{.data.JWT_COOKIE_SAMESITE}' | base64 -d
```

4. **Check for env file formatting issues**:
```bash
# Make sure each variable is on its own line
cat src/prod.env | grep -E "JWT_COOKIE"
```

### Resolution Timeline

**Date**: 2026-01-31

**Issue**: Business plan upgrade failing with login redirect

**Steps Taken**:
1. Fixed CSRF token template variable shadowing (commit 7322b08)
2. Added account ID 2 to `API_EXEMPT_ACCOUNT_IDS`
3. Fixed template CSRF token conditional logic (commit c71a77f)
4. Identified `JWT_COOKIE_SAMESITE=None` as root cause
5. Changed to `JWT_COOKIE_SAMESITE=Lax`
6. Temporarily disabled CSRF to confirm fix
7. Successfully upgraded to Business plan

**Permanent Fix**: Keep `JWT_COOKIE_SAMESITE=Lax` and properly implement CSRF token passing in all forms.

## Issue: JavaScript Fetch Requests Fail with JWT Cookies

### AJAX Symptoms

- Toggle switches or AJAX buttons show "Failed to update" errors
- API returns 401 Unauthorized or 422 Unprocessable Entity
- Browser console shows empty or missing Authorization header
- Form submissions work but JavaScript fetch requests fail

### AJAX Root Cause

#### Problem: Trying to Read HttpOnly Cookies in JavaScript

When JWT is stored in cookies with `HttpOnly=True` (the secure default):
- JavaScript **cannot** read the `access_token_cookie`
- Code like `document.cookie.split(';')` won't find it
- Sending `Authorization: Bearer ${token}` results in an empty token

**Incorrect Pattern**:
```javascript
// This will NOT work - access_token_cookie is HttpOnly
function getAccessToken() {
  const cookies = document.cookie.split(';');
  for (const cookie of cookies) {
    const [name, value] = cookie.trim().split('=');
    if (name === 'access_token_cookie') {
      return value;  // Always empty!
    }
  }
  return '';
}

fetch('/api/endpoint', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${getAccessToken()}`,  // Empty!
    'Content-Type': 'application/json',
  },
  body: JSON.stringify(data),
});
```

**Correct Pattern**:
```javascript
// CSRF token is NOT HttpOnly, so JavaScript can read it
function getCsrfToken() {
  const cookies = document.cookie.split(';');
  for (const cookie of cookies) {
    const [name, value] = cookie.trim().split('=');
    if (name.trim() === 'csrf_access_token') {
      return decodeURIComponent(value);
    }
  }
  return '';
}

// Let browser send JWT cookie automatically
fetch('/api/endpoint', {
  method: 'POST',
  credentials: 'same-origin',  // Required to send cookies!
  headers: {
    'Content-Type': 'application/json',
    'X-CSRF-TOKEN': getCsrfToken(),  // CSRF token in header
  },
  body: JSON.stringify(data),
});
```

### Key Points for AJAX Requests

1. **Don't read JWT from cookies** - It's HttpOnly for security
2. **Don't send Authorization header** - Browser sends cookie automatically
3. **Add `credentials: 'same-origin'`** - Required for cookies to be sent
4. **Send CSRF token in header** - Read from `csrf_access_token` cookie (not HttpOnly)

### AJAX Resolution Timeline

**Date**: 2026-02-01

**Issue**: AI Features toggle failing with "Failed to update draft reply setting"

**Steps Taken**:

1. Identified JavaScript was trying to read HttpOnly `access_token_cookie`
2. Removed `Authorization: Bearer` header (was sending empty token)
3. Added `credentials: 'same-origin'` to fetch request
4. Kept CSRF token header (read from non-HttpOnly `csrf_access_token`)
5. Toggle now works correctly

**Commit**: Fixed in `src/templates/settings/index.html`

### AJAX Related Files

- `src/templates/settings/index.html` - Draft reply toggle JavaScript
- `src/api/v1/inboxiq.py` - API endpoint with `@jwt_required()`

---

## Prevention

1. **Always use `SameSite=Lax`** for same-site applications
2. **Test form submissions** after JWT configuration changes
3. **Monitor logs** for "Missing CSRF token" warnings
4. **Verify cookie presence** in browser DevTools Network tab
5. **Check prod.env file** for formatting issues (no missing newlines)

### Related Files

- `src/config.py` - JWT configuration
- `src/settings/__init__.py` - `login_required_settings` decorator
- `src/settings/routes.py` - Route handlers with CSRF token
- `src/templates/settings/index.html` - Form with CSRF token field
- `src/prod.env` - Production environment variables

### References

- [Flask-JWT-Extended CSRF Protection](https://flask-jwt-extended.readthedocs.io/en/stable/options/#csrf-protection)
- [MDN: SameSite cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie/SameSite)

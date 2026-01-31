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

### Prevention

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

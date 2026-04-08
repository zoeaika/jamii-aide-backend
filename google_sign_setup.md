# Authentication Setup

This backend supports both:

1. Email/password signup and login
2. Google sign-in using a Google ID token

The backend always returns its own JWT tokens after successful authentication.

## Active endpoints

```text
POST /api/auth/register/
POST /api/auth/login/
POST /api/auth/google/
POST /api/auth/refresh/
GET  /api/auth/me/
```

## 1. Email/password auth

Register payload:

```json
{
  "email": "user@example.com",
  "password": "StrongPass123!",
  "first_name": "Jane",
  "last_name": "Doe",
  "current_country": "Kenya",
  "current_city": "Nairobi"
}
```

Login payload:

```json
{
  "email": "user@example.com",
  "password": "StrongPass123!"
}
```

## 2. Google auth flow

The frontend should use Google Identity Services and send the returned `credential`
to the backend.

Google login payload:

```json
{
  "credential": "google_id_token"
}
```

The backend verifies the token with Google, creates or updates the local user,
then returns local JWT access and refresh tokens.

## 3. Required environment variables

Local development:

```env
DEBUG=True
SECRET_KEY=<your-local-secret>
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ORIGINS=http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000
CSRF_TRUSTED_ORIGINS=http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000
GOOGLE_OAUTH_CLIENT_ID=<your-google-web-client-id>
GOOGLE_OAUTH_CLIENT_SECRET=<your-google-client-secret>
```

Production:

```env
DEBUG=False
SECRET_KEY=<strong-random-secret>
ALLOWED_HOSTS=<backend-domain>
CORS_ORIGINS=https://<frontend-domain>
CSRF_TRUSTED_ORIGINS=https://<backend-domain>,https://<frontend-domain>
GOOGLE_OAUTH_CLIENT_ID=<your-google-web-client-id>
GOOGLE_OAUTH_CLIENT_SECRET=<your-google-client-secret>
```

## 4. Google Cloud Console setup

Create an OAuth 2.0 Web Application credential and configure:

Authorized JavaScript origins:

```text
http://localhost:3000
http://localhost:3001
https://<your-frontend-domain>
```

If you later use a redirect-based Google flow, also add the relevant redirect URIs.

## 5. Frontend example

The frontend should send `credentialResponse.credential` to the backend.

```jsx
import { GoogleOAuthProvider, GoogleLogin } from '@react-oauth/google';
import axios from 'axios';

function LoginPage() {
  async function handleGoogleLogin(credentialResponse) {
    const response = await axios.post('http://localhost:8000/api/auth/google/', {
      credential: credentialResponse.credential,
    });

    localStorage.setItem('access_token', response.data.access_token);
    localStorage.setItem('refresh_token', response.data.refresh_token);
  }

  return (
    <GoogleOAuthProvider clientId="YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com">
      <GoogleLogin onSuccess={handleGoogleLogin} />
    </GoogleOAuthProvider>
  );
}
```

## Notes

- Google login does not replace normal signup/login; both are supported.
- Public API registration creates `user` accounts by default.
- New Google users are also created as `user` by default.
- Google accounts must provide a verified email address.
- AWS deployment should use HTTPS and production Google credentials.

# Google OAuth — production setup for app.jamiiaide.com

After deploying the full app to `https://app.jamiiaide.com`, update your Google Cloud OAuth **Web client**:

## Authorized JavaScript origins

Add:

```
https://app.jamiiaide.com
```

Keep for local dev (optional on same client):

```
http://localhost:3000
```

## Authorized redirect URIs

Add any URIs your Django Google auth flow requires. For token-based frontend Google Sign-In (`@react-oauth/google`), origins are usually sufficient; confirm against your backend `google_sign_setup.md`.

## Backend `.env` on Droplet

```env
GOOGLE_OAUTH_CLIENT_ID=<same client ID as frontend NEXT_PUBLIC_GOOGLE_CLIENT_ID>
GOOGLE_OAUTH_CLIENT_SECRET=<client secret>
```

## Frontend Vercel env

```env
NEXT_PUBLIC_GOOGLE_CLIENT_ID=<same client ID>
```

Both frontend and backend must use the **same** OAuth client ID for the production app.

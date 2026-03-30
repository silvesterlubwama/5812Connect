# Test Credentials

## Admin Account
- **Email**: admin@5812uganda.org
- **Password**: Admin@5812
- **Role**: admin
- **Extension**: 2450 (assigned during testing)

## Login Notes
- Login uses `identifier` field (not `email` directly)
- Supports: email, phone, or national ID as identifier

## 2FA Testing
- Admin has TOTP secret stored (for 2FA testing)
- Use any TOTP authenticator app (Google Authenticator, Authy)
- 2FA is currently NOT enabled by default - must be enabled via Settings > Security

## Google OAuth
- Available via "Sign in with Google" button on login page
- Uses Emergent-managed Google OAuth integration

## Calling System
- Extension 2450 assigned to admin user
- Dialer accessible via green phone icon in header
- Extensions must be assigned before users appear in dialer contacts

## SIP/PBX Configuration
- **Provider**: RingTele / SkySwitch
- **Wave Server**: https://5812Uganda.a.gdms.cloud
- **Wave Extension**: 4001
- **Wave Password**: Ucm63042024!

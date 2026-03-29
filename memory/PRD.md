# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global with internal WebRTC calling, unified communications, and optional PBX integration.

## Calling Architecture (Simplified)
- **Internal Calls**: Pure WebRTC peer-to-peer (no PBX needed) — unlimited audio, video, screen sharing, group calls
- **External Calls**: Optional — connect a local PBX (FreePBX/Asterisk) for SIP trunking to real phone numbers
- **SIP.js**: Available but dormant — only activates when PBX is configured with WebSocket URL

## Latest Changes (Iteration 43)
- [x] CallContext rewritten — pure WebRTC focus, clean code, SIP lazy-loaded
- [x] Chat + Calling merged — phone/video buttons in chat header actually initiate calls
- [x] Dialer simplified — staff contacts with hover audio/video buttons, no extension-centric UI
- [x] PBX page kept as "PBX Integration (Advanced)" with info banner
- [x] CallInterface dark-native responsive design for all modes
- [x] Screen sharing, group calls, hold, mute, video toggle all WebRTC-native

## Test Reports
- Iteration 43: 100% (17/17 backend + all frontend verified)

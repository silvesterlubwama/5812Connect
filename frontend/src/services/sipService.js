/**
 * SIP.js Integration Service
 * Handles SIP registration, outbound/inbound calls via PBX WebSocket
 */
let SimpleUser;
try {
  const sipjs = require('sip.js/lib/platform/web');
  SimpleUser = sipjs.SimpleUser;
} catch (e) {
  try {
    const sipjs = require('sip.js');
    SimpleUser = sipjs.Web?.SimpleUser || sipjs.SimpleUser;
  } catch (e2) {
    console.warn('[SIP] sip.js not available:', e2.message);
  }
}

class SipService {
  constructor() {
    this.simpleUser = null;
    this.registered = false;
    this.config = null;
    this.registrationError = null;
    this.onIncomingCall = null;
    this.onCallAnswered = null;
    this.onCallHangup = null;
    this.onRegistered = null;
    this.onUnregistered = null;
    this.onError = null;
  }

  /**
   * Derive WebSocket URL from PBX config if not explicitly set
   */
  _deriveWebSocketUrl(config) {
    if (config.websocket_url) return config.websocket_url;
    // Auto-derive: try wss on port 8089 (common for Asterisk/FreePBX WebRTC)
    const host = (config.host || '').replace(/:\d+$/, ''); // strip port if embedded
    if (!host) return null;
    // Common WebSocket ports: 8089 (FreePBX), 5066 (Kamailio), 7443 (3CX)
    const portMap = { freepbx: 8089, asterisk: 8089, '3cx': 7443, generic_sip: 8089 };
    const wsPort = portMap[config.provider] || 8089;
    return `wss://${host}:${wsPort}/ws`;
  }

  /**
   * Register with a SIP server via WebSocket
   * @param {Object} config - PBX config
   * @param {HTMLMediaElement} remoteAudio - Audio element for remote stream
   */
  async register(config, remoteAudio) {
    if (!SimpleUser) {
      this.registrationError = 'SIP.js library not loaded';
      console.error('[SIP]', this.registrationError);
      throw new Error(this.registrationError);
    }

    if (this.simpleUser) {
      await this.unregister();
    }

    this.config = config;
    const host = (config.host || '').replace(/:\d+$/, '');
    const sipDomain = config.sip_domain || host;
    const wsUrl = this._deriveWebSocketUrl(config);
    const sipUser = config.sip_username;
    const sipPass = config.sip_password || '';

    if (!sipUser || !sipDomain) {
      this.registrationError = 'SIP username and domain required';
      throw new Error(this.registrationError);
    }

    if (!wsUrl) {
      this.registrationError = 'WebSocket URL required (configure or auto-derived from host)';
      throw new Error(this.registrationError);
    }

    const aor = `sip:${sipUser}@${sipDomain}`;
    console.log(`[SIP] Registering ${aor} via ${wsUrl}`);

    const options = {
      aor,
      media: {
        remote: { audio: remoteAudio },
        constraints: { audio: true, video: false },
      },
      userAgentOptions: {
        authorizationUsername: sipUser,
        authorizationPassword: sipPass,
        displayName: config.display_name || sipUser,
        logLevel: 'warn',
        transportOptions: {
          server: wsUrl,
          connectionTimeout: 10,
          keepAliveInterval: 30,
        },
        sessionDescriptionHandlerFactoryOptions: {
          peerConnectionConfiguration: {
            iceServers: [
              { urls: 'stun:stun.l.google.com:19302' },
              ...(config.stun_servers || []).map(s => ({ urls: s })),
            ],
          },
        },
      },
    };

    try {
      this.simpleUser = new SimpleUser(wsUrl, options);

      this.simpleUser.delegate = {
        onCallCreated: () => { console.log('[SIP] Call created'); },
        onCallReceived: () => {
          console.log('[SIP] Incoming call');
          if (this.onIncomingCall) {
            const from = this.simpleUser.session?.remoteIdentity?.uri?.toString() || 'Unknown';
            this.onIncomingCall({ type: 'sip_incoming', from, caller_name: from });
          }
        },
        onCallAnswered: () => { console.log('[SIP] Answered'); if (this.onCallAnswered) this.onCallAnswered(); },
        onCallHangup: () => { console.log('[SIP] Hangup'); if (this.onCallHangup) this.onCallHangup(); },
        onRegistered: () => {
          console.log('[SIP] Registered successfully');
          this.registered = true;
          this.registrationError = null;
          if (this.onRegistered) this.onRegistered();
        },
        onUnregistered: () => {
          console.log('[SIP] Unregistered');
          this.registered = false;
          if (this.onUnregistered) this.onUnregistered();
        },
        onServerConnect: () => { console.log('[SIP] Transport connected'); },
        onServerDisconnect: (error) => {
          console.log('[SIP] Transport disconnected', error?.message || '');
          this.registered = false;
          this.registrationError = `Transport disconnected: ${error?.message || 'unknown'}`;
          if (this.onError) this.onError(this.registrationError);
        },
      };

      await this.simpleUser.connect();
      await this.simpleUser.register();
      return true;
    } catch (err) {
      console.error('[SIP] Registration failed:', err.message);
      this.registered = false;
      this.registrationError = err.message;
      throw err;
    }
  }

  async unregister() {
    if (this.simpleUser) {
      try {
        if (this.registered) await this.simpleUser.unregister();
        await this.simpleUser.disconnect();
      } catch (e) { console.warn('[SIP] Unregister:', e.message); }
      this.simpleUser = null;
      this.registered = false;
    }
  }

  async call(target) {
    if (!this.simpleUser || !this.registered) throw new Error('Not registered');
    const domain = this.config.sip_domain || (this.config.host || '').replace(/:\d+$/, '');
    const uri = target.includes('@') ? `sip:${target}` : `sip:${target}@${domain}`;
    console.log(`[SIP] Calling ${uri}`);
    await this.simpleUser.call(uri);
  }

  async answer() { if (this.simpleUser) await this.simpleUser.answer(); }
  async hangup() { if (this.simpleUser) await this.simpleUser.hangup(); }
  async hold() { if (this.simpleUser) await this.simpleUser.hold(); }
  async unhold() { if (this.simpleUser) await this.simpleUser.unhold(); }
  async mute() { if (this.simpleUser) await this.simpleUser.mute(); }
  async unmute() { if (this.simpleUser) await this.simpleUser.unmute(); }
  async sendDtmf(tone) { if (this.simpleUser) await this.simpleUser.sendDTMF(tone); }

  async transfer(target) {
    if (!this.simpleUser?.session) throw new Error('No active call');
    const domain = this.config.sip_domain || (this.config.host || '').replace(/:\d+$/, '');
    const uri = target.includes('@') ? `sip:${target}` : `sip:${target}@${domain}`;
    if (this.simpleUser.session.refer) await this.simpleUser.session.refer(uri);
  }

  get isRegistered() { return this.registered; }
  get isOnCall() { return !!this.simpleUser?.session; }
  get lastError() { return this.registrationError; }
}

const sipService = new SipService();
export default sipService;

/**
 * SIP.js Integration Service (lazy-loaded, safe for production builds)
 */
let SimpleUser = null;

// Safe dynamic import - won't crash if sip.js bundle structure differs
function loadSipJs() {
  if (SimpleUser) return true;
  try {
    // Try the standard import path
    const mod = require('sip.js');
    SimpleUser = mod?.Web?.SimpleUser || mod?.SimpleUser;
    if (!SimpleUser) {
      try {
        const webMod = require('sip.js/lib/platform/web');
        SimpleUser = webMod?.SimpleUser;
      } catch (e2) { console.debug('[SIP] Alternate import path unavailable:', e2.message); }
    }
  } catch (e) {
    console.warn('[SIP] sip.js not available:', e.message);
  }
  return !!SimpleUser;
}

class SipService {
  constructor() {
    this.simpleUser = null;
    this.registered = false;
    this.config = null;
    this.registrationError = null;
    this.activeWsUrl = null;
    this.onIncomingCall = null;
    this.onCallAnswered = null;
    this.onCallHangup = null;
    this.onRegistered = null;
    this.onUnregistered = null;
    this.onError = null;
  }

  /**
   * Generate list of WebSocket URLs to try
   */
  _getWsUrls(config) {
    const urls = [];
    if (config.websocket_url) urls.push(config.websocket_url);
    const host = (config.host || '').replace(/:\d+$/, '');
    if (host) {
      // SkySwitch/ConnectUC style
      if (!urls.includes(`wss://${host}:443/ws`)) urls.push(`wss://${host}:443/ws`);
      if (!urls.includes(`wss://${host}:9002`)) urls.push(`wss://${host}:9002`);
      if (!urls.includes(`wss://${host}:8089/ws`)) urls.push(`wss://${host}:8089/ws`);
      if (!urls.includes(`wss://${host}:443`)) urls.push(`wss://${host}:443`);
    }
    return urls;
  }

  /**
   * Build ICE servers config from PBX config
   */
  _buildIceServers(config) {
    const servers = [];
    // Add STUN servers
    (config.stun_servers || []).forEach(s => {
      if (typeof s === 'string') servers.push({ urls: s });
      else servers.push(s);
    });
    // Add TURN servers with credentials
    (config.turn_servers || []).forEach(t => {
      servers.push({
        urls: t.urls || t,
        username: t.username || config.sip_username || '',
        credential: t.credential || config.sip_password || '',
      });
    });
    // Always include Google STUN as fallback
    if (!servers.some(s => (s.urls || '').includes('google'))) {
      servers.push({ urls: 'stun:stun.l.google.com:19302' });
    }
    return servers;
  }

  /**
   * Register with a SIP server — tries multiple WebSocket URLs
   */
  async register(config, remoteAudio) {
    if (!loadSipJs() || !SimpleUser) {
      this.registrationError = 'SIP.js library not available';
      throw new Error(this.registrationError);
    }
    if (this.simpleUser) await this.unregister();

    this.config = config;
    const host = (config.host || '').replace(/:\d+$/, '');
    const sipDomain = config.sip_domain || host;
    const sipUser = config.sip_username;
    const sipPass = config.sip_password || '';

    if (!sipUser || !sipDomain) {
      this.registrationError = 'SIP username and domain required';
      throw new Error(this.registrationError);
    }

    const wsUrls = this._getWsUrls(config);
    if (wsUrls.length === 0) {
      this.registrationError = 'No WebSocket URL available';
      throw new Error(this.registrationError);
    }

    const aor = `sip:${sipUser}@${sipDomain}`;
    const iceServers = config.sip_only ? [] : this._buildIceServers(config);
    let lastError = null;

    // Try each WebSocket URL
    for (const wsUrl of wsUrls) {
      console.log(`[SIP] Trying ${aor} via ${wsUrl}`);
      try {
        await this._attemptRegister(wsUrl, aor, sipUser, sipPass, iceServers, remoteAudio, config);
        this.activeWsUrl = wsUrl;
        console.log(`[SIP] Registered successfully via ${wsUrl}`);
        return true;
      } catch (err) {
        lastError = err;
        console.warn(`[SIP] Failed on ${wsUrl}: ${err.message}`);
        // Clean up before trying next
        if (this.simpleUser) {
          try { await this.simpleUser.disconnect(); } catch (e) { console.warn("[SIP]", e.message); }
          this.simpleUser = null;
        }
      }
    }

    this.registrationError = `All WebSocket URLs failed. Last error: ${lastError?.message || 'unknown'}`;
    throw new Error(this.registrationError);
  }

  async _attemptRegister(wsUrl, aor, sipUser, sipPass, iceServers, remoteAudio, config) {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error(`Connection timeout on ${wsUrl}`));
      }, 12000);

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
            peerConnectionConfiguration: { iceServers },
            constraints: { audio: true, video: false },
          },
        },
      };

      try {
        this.simpleUser = new SimpleUser(wsUrl, options);

        this.simpleUser.delegate = {
          onCallCreated: () => console.log('[SIP] Call created'),
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
            clearTimeout(timeout);
            console.log('[SIP] Registered');
            this.registered = true;
            this.registrationError = null;
            if (this.onRegistered) this.onRegistered();
            resolve(true);
          },
          onUnregistered: () => {
            this.registered = false;
            if (this.onUnregistered) this.onUnregistered();
          },
          onServerConnect: () => console.log('[SIP] Transport connected'),
          onServerDisconnect: (error) => {
            clearTimeout(timeout);
            this.registered = false;
            const msg = `Transport disconnected: ${error?.message || 'unknown'}`;
            this.registrationError = msg;
            if (this.onError) this.onError(msg);
            reject(new Error(msg));
          },
        };

        this.simpleUser.connect().then(() => {
          return this.simpleUser.register();
        }).catch(err => {
          clearTimeout(timeout);
          reject(err);
        });
      } catch (err) {
        clearTimeout(timeout);
        reject(err);
      }
    });
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
  get connectedUrl() { return this.activeWsUrl; }
}

const sipService = new SipService();
export default sipService;

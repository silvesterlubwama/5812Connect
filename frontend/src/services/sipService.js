/**
 * SIP.js Integration Service
 * Handles SIP registration, outbound/inbound calls via PBX WebSocket
 */
import { SimpleUser, SimpleUserOptions } from 'sip.js/lib/platform/web';

class SipService {
  constructor() {
    this.simpleUser = null;
    this.registered = false;
    this.config = null;
    this.onIncomingCall = null;
    this.onCallAnswered = null;
    this.onCallHangup = null;
    this.onRegistered = null;
    this.onUnregistered = null;
    this.onError = null;
  }

  /**
   * Register with a SIP server via WebSocket
   * @param {Object} config - PBX config with sip_username, sip_password, sip_domain, websocket_url
   * @param {HTMLMediaElement} remoteAudio - Audio element for remote stream
   */
  async register(config, remoteAudio) {
    if (this.simpleUser) {
      await this.unregister();
    }

    this.config = config;
    const sipDomain = config.sip_domain || config.host;
    const wsUrl = config.websocket_url;
    const sipUser = config.sip_username;
    const sipPass = config.sip_password;

    if (!wsUrl || !sipUser || !sipDomain) {
      throw new Error('SIP WebSocket URL, username, and domain are required');
    }

    const aor = `sip:${sipUser}@${sipDomain}`;

    const options = {
      aor,
      media: {
        remote: { audio: remoteAudio },
        constraints: { audio: true, video: false },
      },
      userAgentOptions: {
        authorizationUsername: sipUser,
        authorizationPassword: sipPass || '',
        displayName: config.display_name || sipUser,
        logLevel: 'warn',
        transportOptions: {
          server: wsUrl,
        },
      },
    };

    try {
      this.simpleUser = new SimpleUser(wsUrl, options);

      // Set up delegates
      this.simpleUser.delegate = {
        onCallCreated: () => {
          console.log('[SIP] Call created');
        },
        onCallReceived: () => {
          console.log('[SIP] Incoming call');
          if (this.onIncomingCall) {
            this.onIncomingCall({
              type: 'sip_incoming',
              from: this.simpleUser.session?.remoteIdentity?.uri?.toString() || 'Unknown',
            });
          }
        },
        onCallAnswered: () => {
          console.log('[SIP] Call answered');
          if (this.onCallAnswered) this.onCallAnswered();
        },
        onCallHangup: () => {
          console.log('[SIP] Call hangup');
          if (this.onCallHangup) this.onCallHangup();
        },
        onRegistered: () => {
          console.log('[SIP] Registered');
          this.registered = true;
          if (this.onRegistered) this.onRegistered();
        },
        onUnregistered: () => {
          console.log('[SIP] Unregistered');
          this.registered = false;
          if (this.onUnregistered) this.onUnregistered();
        },
        onServerConnect: () => {
          console.log('[SIP] Server connected');
        },
        onServerDisconnect: (error) => {
          console.log('[SIP] Server disconnected', error);
          this.registered = false;
          if (this.onError) this.onError('SIP server disconnected');
        },
      };

      await this.simpleUser.connect();
      await this.simpleUser.register();
      return true;
    } catch (err) {
      console.error('[SIP] Registration failed:', err);
      this.registered = false;
      throw err;
    }
  }

  async unregister() {
    if (this.simpleUser) {
      try {
        if (this.registered) {
          await this.simpleUser.unregister();
        }
        await this.simpleUser.disconnect();
      } catch (e) {
        console.warn('[SIP] Unregister error:', e);
      }
      this.simpleUser = null;
      this.registered = false;
    }
  }

  /**
   * Make an outbound SIP call
   * @param {string} target - SIP URI or extension number
   */
  async call(target) {
    if (!this.simpleUser || !this.registered) {
      throw new Error('Not registered with SIP server');
    }
    const sipDomain = this.config.sip_domain || this.config.host;
    const uri = target.includes('@') ? `sip:${target}` : `sip:${target}@${sipDomain}`;
    await this.simpleUser.call(uri, {
      inviteWithoutSdp: false,
    });
  }

  async answer() {
    if (!this.simpleUser) throw new Error('No SIP connection');
    await this.simpleUser.answer();
  }

  async hangup() {
    if (!this.simpleUser) return;
    await this.simpleUser.hangup();
  }

  async hold() {
    if (!this.simpleUser) return;
    await this.simpleUser.hold();
  }

  async unhold() {
    if (!this.simpleUser) return;
    await this.simpleUser.unhold();
  }

  async mute() {
    if (!this.simpleUser) return;
    await this.simpleUser.mute();
  }

  async unmute() {
    if (!this.simpleUser) return;
    await this.simpleUser.unmute();
  }

  async sendDtmf(tone) {
    if (!this.simpleUser) return;
    await this.simpleUser.sendDTMF(tone);
  }

  /**
   * Transfer active call to another extension
   * @param {string} target - Extension or SIP URI to transfer to
   */
  async transfer(target) {
    if (!this.simpleUser?.session) throw new Error('No active call');
    const sipDomain = this.config.sip_domain || this.config.host;
    const uri = target.includes('@') ? `sip:${target}` : `sip:${target}@${sipDomain}`;
    // Blind transfer
    const session = this.simpleUser.session;
    if (session && session.refer) {
      await session.refer(uri);
    }
  }

  get isRegistered() {
    return this.registered;
  }

  get isOnCall() {
    return !!this.simpleUser?.session;
  }
}

// Singleton instance
const sipService = new SipService();
export default sipService;

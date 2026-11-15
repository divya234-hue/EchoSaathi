/**
 * Talk mode: the phone is the microphone and the speaker (`?mode=talk`).
 *
 * Prisma takes exactly 1024 bytes of 16 kHz mono s16le every 32 ms. A
 * MediaRecorder cannot produce that — it emits WebM/Opus — so capture is an
 * AudioWorklet that resamples the device rate and posts one whole frame per
 * 512 samples (1024 bytes). The same AudioContext plays Timbre's reply PCM,
 * scheduled as the chunks arrive.
 *
 * `Talk.start()` must be called from a user gesture: iOS and Chrome only let
 * an AudioContext start (and only show the microphone prompt) inside one.
 * Half-duplex is the caller's job too: `setMuted(true)` while the reply plays,
 * so the phone never hears itself — the page's half of DECISIONS D-005.
 */

const WORKLET = `
class PashyantiCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.pos = 0;
    this.prev = null;
    this.frame = new Int16Array(512);
    this.fill = 0;
  }

  process(inputs) {
    const input = inputs[0] && inputs[0][0];
    if (!input || input.length === 0) return true;
    if (this.prev === null) this.prev = input[0];
    const n = input.length;
    // Linear interpolation from the device rate to 16 kHz. Each output sits
    // between x(i-1) and x(i); x(-1) is the last sample of the previous block,
    // so a block boundary is not a click.
    while (this.pos < n) {
      const i = Math.floor(this.pos);
      const a = i < 1 ? this.prev : input[i - 1];
      const b = input[i];
      const frac = this.pos - i;
      const sample = a + (b - a) * frac;
      let v = Math.round(sample * 32767);
      v = v > 32767 ? 32767 : v < -32768 ? -32768 : v;
      this.frame[this.fill++] = v;
      if (this.fill === this.frame.length) {
        this.port.postMessage(this.frame.slice().buffer);
        this.fill = 0;
      }
      this.pos += this.ratio;
    }
    this.pos -= n;
    this.prev = input[n - 1];
    return true;
  }
}
registerProcessor("pashyanti-capture", PashyantiCapture);
`;

export type TalkOptions = {
  /** One 1024-byte frame of 16 kHz s16le PCM. */
  onFrame: (frame: ArrayBuffer) => void;
  /** The reply has finished playing on this device. */
  onPlaybackDrained: () => void;
};

export type TalkFailure = "denied" | "insecure" | "unsupported";

export class Talk {
  private readonly ctx: AudioContext;
  private readonly stream: MediaStream;
  private readonly node: AudioWorkletNode;
  private readonly player: PcmPlayer;
  private muted = false;

  private constructor(
    ctx: AudioContext,
    stream: MediaStream,
    node: AudioWorkletNode,
    player: PcmPlayer,
  ) {
    this.ctx = ctx;
    this.stream = stream;
    this.node = node;
    this.player = player;
  }

  static async start(options: TalkOptions): Promise<Talk> {
    if (typeof window === "undefined" || !window.isSecureContext) {
      throw new TalkError("insecure");
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) {
      throw new TalkError("unsupported");
    }

    const ctx = new AudioContext({ latencyHint: "interactive" });
    try {
      // The tap is the gesture iOS wants; Chrome starts suspended.
      await ctx.resume();
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
        },
      });
      let node: AudioWorkletNode;
      const url = URL.createObjectURL(
        new Blob([WORKLET], { type: "text/javascript" }),
      );
      try {
        await ctx.audioWorklet.addModule(url);
        node = new AudioWorkletNode(ctx, "pashyanti-capture", {
          numberOfInputs: 1,
          numberOfOutputs: 1,
          outputChannelCount: [1],
        });
      } finally {
        URL.revokeObjectURL(url);
      }

      const source = ctx.createMediaStreamSource(stream);
      const silent = ctx.createGain();
      silent.gain.value = 0;
      // A node with no path to the destination is not pulled; gain 0 keeps the
      // graph alive without playing the microphone back into the speaker.
      source.connect(node).connect(silent).connect(ctx.destination);

      const player = new PcmPlayer(ctx);
      const talk = new Talk(ctx, stream, node, player);
      player.onDrain = () => options.onPlaybackDrained();
      node.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
        if (!talk.muted) options.onFrame(event.data);
      };
      return talk;
    } catch (err) {
      void ctx.close();
      if (err instanceof DOMException) {
        if (err.name === "NotAllowedError" || err.name === "SecurityError") {
          throw new TalkError("denied");
        }
      }
      throw err;
    }
  }

  /** Half-duplex: stop sending frames while our own reply plays. */
  setMuted(muted: boolean) {
    this.muted = muted;
  }

  /** Queue one base64 PCM chunk of Timbre audio. */
  play(data: string, rate: number) {
    this.player.enqueue(data, rate);
  }

  get playing(): boolean {
    return this.player.busy;
  }

  stop() {
    this.node.port.onmessage = null;
    this.player.stop();
    for (const track of this.stream.getTracks()) track.stop();
    void this.ctx.close();
  }
}

export class TalkError extends Error {
  readonly kind: TalkFailure;

  constructor(kind: TalkFailure) {
    super(`talk mode: ${kind}`);
    this.kind = kind;
  }
}

/** Schedules s16le PCM chunks back to back through Web Audio. */
class PcmPlayer {
  private readonly ctx: AudioContext;
  private readonly live = new Set<AudioBufferSourceNode>();
  private nextAt = 0;
  onDrain: (() => void) | null = null;

  constructor(ctx: AudioContext) {
    this.ctx = ctx;
  }

  get busy(): boolean {
    return this.live.size > 0;
  }

  enqueue(base64: string, rate: number) {
    const binary = atob(base64);
    if (binary.length < 2) return;
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    const samples = Math.floor(bytes.length / 2);
    const view = new DataView(bytes.buffer);
    const buffer = this.ctx.createBuffer(1, samples, rate);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < samples; i += 1) {
      channel[i] = view.getInt16(i * 2, true) / 32768;
    }

    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(this.ctx.destination);
    const startAt = Math.max(this.ctx.currentTime + 0.06, this.nextAt);
    source.start(startAt);
    this.nextAt = startAt + buffer.duration;
    this.live.add(source);
    source.onended = () => {
      this.live.delete(source);
      if (this.live.size === 0) this.onDrain?.();
    };
  }

  stop() {
    for (const source of this.live) {
      try {
        source.stop();
      } catch {
        /* already ended */
      }
    }
    this.live.clear();
    this.nextAt = 0;
  }
}

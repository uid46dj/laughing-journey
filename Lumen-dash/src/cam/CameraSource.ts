export type CameraErrorKind = 'denied' | 'no-device' | 'busy' | 'insecure' | 'unknown';

export class CameraError extends Error {
  constructor(
    public kind: CameraErrorKind,
    message: string,
  ) {
    super(message);
  }
}

/** Owns the webcam stream and the (hidden) <video> element that feeds the pose estimator. */
export class CameraSource {
  readonly video: HTMLVideoElement;
  private stream: MediaStream | null = null;
  onEnded: (() => void) | null = null;

  constructor() {
    this.video = document.createElement('video');
    this.video.muted = true;
    this.video.playsInline = true;
    this.video.autoplay = true;
  }

  get active() {
    return this.stream !== null;
  }

  async listDevices(): Promise<MediaDeviceInfo[]> {
    if (!navigator.mediaDevices?.enumerateDevices) return [];
    const all = await navigator.mediaDevices.enumerateDevices();
    return all.filter((d) => d.kind === 'videoinput');
  }

  async start(deviceId?: string): Promise<void> {
    this.stop();
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      throw new CameraError(
        'insecure',
        'The camera needs a secure page (https:// or localhost). You can still play with the keyboard.',
      );
    }
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          frameRate: { ideal: 30 },
          ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
        },
        audio: false,
      });
    } catch (e) {
      const name = (e as DOMException)?.name;
      if (name === 'NotAllowedError' || name === 'SecurityError')
        throw new CameraError('denied', 'Camera access was denied. Allow the camera in your browser, or play with the keyboard.');
      if (name === 'NotFoundError' || name === 'OverconstrainedError')
        throw new CameraError('no-device', 'No camera was found. Plug one in, or play with the keyboard.');
      if (name === 'NotReadableError' || name === 'AbortError')
        throw new CameraError('busy', 'The camera is busy in another app. Close it and retry.');
      throw new CameraError('unknown', `Could not start the camera (${name ?? 'unknown error'}).`);
    }
    this.stream.getVideoTracks().forEach((t) => {
      t.onended = () => this.onEnded?.();
    });
    this.video.srcObject = this.stream;
    await this.video.play();
  }

  stop() {
    this.stream?.getTracks().forEach((t) => {
      t.onended = null;
      t.stop();
    });
    this.stream = null;
    this.video.srcObject = null;
  }
}

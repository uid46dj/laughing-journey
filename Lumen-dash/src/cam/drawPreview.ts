import { SKELETON_EDGES } from './poseTypes';
import type { PoseFrame } from './poseTypes';

/**
 * Draws the webcam image plus skeleton onto a canvas.
 *
 * mirror flips left/right; flipY flips upside down (camera mounted rotated, phone in a case).
 *
 * Only the DRAWING is flipped, never the video itself: landmarks must stay in real image
 * space, because the gesture engine compares hip height to shoulder height and tracks upward
 * motion. Feeding it an inverted image would make crouch read as jump. So the picture is
 * flipped here and the landmark Y is flipped back for the overlay, and the two line up.
 */
export function drawPreview(
  canvas: HTMLCanvasElement,
  video: HTMLVideoElement,
  frame: PoseFrame | null,
  mirror: boolean,
  color: string,
  flipY = false,
) {
  const ctx = canvas.getContext('2d');
  if (!ctx || video.readyState < 2) return;
  const w = canvas.width;
  const h = canvas.height;
  ctx.save();
  if (flipY) {
    ctx.translate(0, h);
    ctx.scale(1, -1);
  }
  if (mirror) {
    ctx.translate(w, 0);
    ctx.scale(-1, 1);
  }
  ctx.drawImage(video, 0, 0, w, h);
  if (frame) {
    const lm = frame.landmarks;
    // landmarks come from the unflipped image, so undo flipY for the overlay
    const yOf = (p: { y: number }) => (flipY ? (1 - p.y) * h : p.y * h);
    ctx.lineWidth = 3;
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineCap = 'round';
    for (const [a, b] of SKELETON_EDGES) {
      const p = lm[a];
      const q = lm[b];
      if (!p || !q || p.visibility < 0.5 || q.visibility < 0.5) continue;
      ctx.beginPath();
      ctx.moveTo(p.x * w, yOf(p));
      ctx.lineTo(q.x * w, yOf(q));
      ctx.stroke();
    }
    for (const i of [0, 11, 12, 13, 14, 15, 16]) {
      const p = lm[i];
      if (!p || p.visibility < 0.5) continue;
      ctx.beginPath();
      ctx.arc(p.x * w, yOf(p), i === 0 ? 6 : 4, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.restore();
}

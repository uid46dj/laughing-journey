import { LM } from './poseTypes';
import type { PoseFrame } from './poseTypes';
import { GESTURE_CONFIG as C } from './gestureConfig';
import type { FramingAssessment } from './gestureTypes';

/** Plain-language guidance for the calibration screen. */
export function assessFraming(frame: PoseFrame | null): FramingAssessment {
  if (!frame) {
    return { status: 'no-pose', message: "We can't see you yet. Step into view so your head and shoulders show." };
  }
  const nose = frame.landmarks[LM.NOSE];
  const ls = frame.landmarks[LM.L_SHOULDER];
  const rs = frame.landmarks[LM.R_SHOULDER];
  if (!nose || !ls || !rs || nose.visibility < C.minVisibility || ls.visibility < C.minVisibility || rs.visibility < C.minVisibility) {
    return { status: 'no-pose', message: 'Show your head and both shoulders to the camera.' };
  }
  const sw = Math.abs(ls.x - rs.x);
  if (sw < C.calibration.minShoulderWidth) return { status: 'too-far', message: 'Move a little closer.' };
  if (sw > C.calibration.maxShoulderWidth) return { status: 'too-close', message: 'Move back a little.' };
  const midX = (ls.x + rs.x) / 2;
  if (Math.abs(midX - 0.5) > C.calibration.maxCenterOffset) {
    // Preview is mirrored: being on the left of the screen means stepping to YOUR right.
    return {
      status: 'off-center',
      message: midX > 0.5 ? 'Step a little to your right, into the middle.' : 'Step a little to your left, into the middle.',
    };
  }
  if (nose.y < 0.14) return { status: 'head-high', message: 'Move back — you need room above your head to jump.' };
  if ((ls.y + rs.y) / 2 > 0.82) return { status: 'low-shoulders', message: 'Tilt the screen up or move back — your shoulders are at the bottom edge.' };
  return { status: 'ok', message: 'Perfect. Hold still…' };
}

/**
 * All gesture thresholds live here. Units: "SW" = shoulder-widths measured at calibration, so values
 * are independent of how far you stand from the camera. A global sensitivity (0.7..1.4) DIVIDES
 * every displacement/velocity threshold: higher sensitivity = smaller movements are enough.
 */
export const GESTURE_CONFIG = {
  /** Visibility required for nose + both shoulders. */
  minVisibility: 0.5,
  /** No valid pose for this long => tracking 'lost' (shorter => 'degraded', state is held). */
  lostAfterMs: 400,

  /** Vertical signal = shoulders (1-w) blended with nose (w). Nose adds jump responsiveness. */
  noseWeight: 0.4,

  /** Lateral zones (SW). Enter further out than exit => hysteresis, no flicker at the boundary. */
  lateralEnter: 0.55,
  lateralExit: 0.3,
  zoneStableFrames: 2,

  /** Jump: needs displacement above neutral AND rising speed, fires on the rising edge. */
  jumpDisplacement: 0.22,
  jumpVelocity: 1.6, // SW per second
  jumpVelocityMinDtMs: 50,
  jumpVelocityWindowMs: 150,
  jumpRefractoryMs: 450,
  postCrouchJumpLockoutMs: 350,

  /** Crouch: shoulders drop below neutral. Negative numbers. */
  crouchEnter: -0.35,
  crouchExit: -0.18,
  crouchStableFrames: 2,
  /** Landing from a jump can dip the shoulders; ignore crouch right after a jump. */
  postJumpCrouchLockoutMs: 650,

  /** Hands-up-and-hold (pause / restart). */
  handsUpHoldMs: 1000,
  wristVisibility: 0.6,

  /** Slow drift correction of the neutral pose while standing still. */
  driftTauMs: 8000,

  calibration: {
    holdMs: 1500,
    minFrames: 8,
    /** Shoulder width as a fraction of frame width. */
    minShoulderWidth: 0.12,
    maxShoulderWidth: 0.45,
    /** Max distance of shoulder midpoint from the frame center (fraction of width). */
    maxCenterOffset: 0.2,
  },
} as const;

import type { InputSource, RunnerInput } from './InputSource';

const BLOCKED = new Set(['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Space']);

/** Dev + accessibility fallback: arrows / WASD / space / ctrl, Esc or P to pause. */
export class KeyboardInputSource implements InputSource {
  private down = new Set<string>();
  private step = 0;
  private jump = false;
  private pause = false;

  attach() {
    window.addEventListener('keydown', this.onDown);
    window.addEventListener('keyup', this.onUp);
    window.addEventListener('blur', this.onBlur);
  }

  detach() {
    window.removeEventListener('keydown', this.onDown);
    window.removeEventListener('keyup', this.onUp);
    window.removeEventListener('blur', this.onBlur);
  }

  private onBlur = () => this.down.clear();

  private onDown = (e: KeyboardEvent) => {
    if (BLOCKED.has(e.code)) e.preventDefault();
    if (!e.repeat) {
      switch (e.code) {
        case 'ArrowLeft':
        case 'KeyA':
          this.step = -1;
          break;
        case 'ArrowRight':
        case 'KeyD':
          this.step = 1;
          break;
        case 'ArrowUp':
        case 'KeyW':
        case 'Space':
          this.jump = true;
          break;
        case 'Escape':
        case 'KeyP':
          this.pause = true;
          break;
      }
    }
    this.down.add(e.code);
  };

  private onUp = (e: KeyboardEvent) => {
    this.down.delete(e.code);
  };

  poll(): RunnerInput {
    const out: RunnerInput = {
      targetLane: null,
      laneStep: this.step as -1 | 0 | 1,
      jumpPressed: this.jump,
      slideHeld: this.down.has('ArrowDown') || this.down.has('KeyS') || this.down.has('ControlLeft') || this.down.has('ControlRight'),
      pausePressed: this.pause,
      jogCadence: null,
      trackingState: 'n/a',
    };
    this.step = 0;
    this.jump = false;
    this.pause = false;
    return out;
  }
}

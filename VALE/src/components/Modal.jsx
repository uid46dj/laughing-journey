import { useLayoutEffect, useRef } from 'react';

// A second dialog must not unlock the page while the first is still open.
const scrollLocks = new WeakMap();

function lockBodyScroll(document) {
  const existingLock = scrollLocks.get(document);
  if (existingLock) {
    existingLock.count += 1;
  } else {
    const body = document.body;
    const style = body.style;
    const properties = ['overflow-x', 'overflow-y', 'padding-right'];
    const previousStyles = properties.map((property) => ({
      property,
      value: style.getPropertyValue(property),
      priority: style.getPropertyPriority(property),
    }));
    const paddingRight = parseFloat(document.defaultView.getComputedStyle(body).paddingRight) || 0;
    const previousWidth = document.documentElement.clientWidth;

    style.setProperty('overflow-x', 'hidden', 'important');
    style.setProperty('overflow-y', 'hidden', 'important');

    // Measure the actual removed gutter, so scrollbar-gutter: stable is not
    // compensated twice and existing body padding is preserved.
    const scrollbarGap = Math.max(0, document.documentElement.clientWidth - previousWidth);
    if (scrollbarGap) {
      style.setProperty('padding-right', `${paddingRight + scrollbarGap}px`, 'important');
    }

    scrollLocks.set(document, { count: 1, style, previousStyles });
  }

  let released = false;
  return () => {
    if (released) return;
    released = true;
    const lock = scrollLocks.get(document);
    if (!lock || --lock.count > 0) return;

    lock.previousStyles.forEach(({ property, value, priority }) => {
      if (value) lock.style.setProperty(property, value, priority);
      else lock.style.removeProperty(property);
    });
    scrollLocks.delete(document);
  };
}

function isBackdropEvent(event) {
  const dialog = event.currentTarget;
  if (event.target !== dialog) return false;
  const bounds = dialog.getBoundingClientRect();
  return event.clientX < bounds.left || event.clientX > bounds.right
    || event.clientY < bounds.top || event.clientY > bounds.bottom;
}

export default function Modal({
  open,
  onClose,
  titleId,
  descriptionId,
  children,
  className = '',
}) {
  const dialogRef = useRef(null);
  const backdropPress = useRef(null);

  useLayoutEffect(() => {
    if (!open) return undefined;
    const dialog = dialogRef.current;
    const document = dialog.ownerDocument;
    const previousFocus = document.activeElement;
    const releaseScroll = lockBodyScroll(document);

    // Never render an open attribute: showModal supplies the native focus trap,
    // inert background and top layer. The guard also supports StrictMode replay.
    try {
      if (!dialog.open) dialog.showModal();
    } catch (error) {
      releaseScroll();
      throw error;
    }

    return () => {
      backdropPress.current = null;
      const activeElement = document.activeElement;
      const shouldRestoreFocus = dialog.contains(activeElement) || activeElement === document.body;
      if (dialog.open) dialog.close();
      releaseScroll();
      // Do not steal focus if the caller has deliberately moved it elsewhere.
      if (shouldRestoreFocus && previousFocus?.isConnected && typeof previousFocus.focus === 'function') {
        previousFocus.focus({ preventScroll: true });
      }
    };
  }, [open]);

  const handlePointerDown = (event) => {
    backdropPress.current = event.button === 0 && event.isPrimary !== false && isBackdropEvent(event)
      ? { pointerId: event.pointerId, released: false }
      : null;
  };

  const handlePointerUp = (event) => {
    const press = backdropPress.current;
    if (!press) return;
    if (press.pointerId === event.pointerId && isBackdropEvent(event)) press.released = true;
    else backdropPress.current = null;
  };

  const handleBackdropClick = (event) => {
    const shouldClose = backdropPress.current?.released && isBackdropEvent(event);
    backdropPress.current = null;
    // Wait for the completed click, rather than closing under a pointer-up.
    if (shouldClose) onClose();
  };

  return (
    <dialog
      ref={dialogRef}
      className={`vale-dialog ${className}`.trim()}
      aria-labelledby={titleId || undefined}
      aria-label={titleId ? undefined : 'Dialog'}
      aria-describedby={descriptionId || undefined}
      aria-modal="true"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClose={(event) => {
        // Ignore queued close events from an effect cleanup or StrictMode replay.
        // Still synchronise a native close (for example, a method="dialog" form).
        if (open && !event.currentTarget.open) onClose();
      }}
      onKeyDown={(event) => {
        if (event.key !== 'Tab') return;
        // Native modality makes the page inert; wrap the edges explicitly so
        // keyboard navigation does not disappear into browser chrome.
        const controls = [...event.currentTarget.querySelectorAll(
          'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
        )].filter((element) => element.getClientRects().length > 0);
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (event.shiftKey && event.target === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && event.target === last) {
          event.preventDefault();
          first?.focus();
        }
      }}
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerUp}
      onPointerCancel={() => { backdropPress.current = null; }}
      onClick={handleBackdropClick}
    >
      <div className="dialog-surface">
        <button className="dialog-close" type="button" aria-label="Close dialog" onClick={onClose}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" focusable="false">
            <path d="m6 6 12 12M18 6 6 18" />
          </svg>
        </button>
        {children}
      </div>
    </dialog>
  );
}

import { useEffect, useId, useState } from 'react';
import Modal from './Modal.jsx';

export default function ReservationDialog({ open, onClose, engraving = '', onEdit }) {
  const id = useId();
  const titleId = `${id}-title`;
  const descriptionId = `${id}-description`;
  const [saveMessage, setSaveMessage] = useState('');
  const [downloadMessage, setDownloadMessage] = useState('');
  const displayEngraving = engraving.trim() || 'No engraving';

  useEffect(() => {
    setSaveMessage('');
    setDownloadMessage('');
  }, [open, engraving]);

  const saveSelection = () => {
    setDownloadMessage('');
    try {
      window.localStorage.setItem('vale-selection', JSON.stringify({
        product: 'Obsidian No. 01',
        engraving,
        priceGBP: 285,
      }));
      setSaveMessage('Selection saved on this device. No reservation has been placed.');
    } catch {
      setSaveMessage('Your selection could not be saved on this device. You can download a copy instead. No reservation has been placed.');
    }
  };

  const downloadSelection = () => {
    const summary = [
      'VALÉ — Your selection',
      '',
      'Product: Obsidian No. 01',
      'Edition 01 / 250',
      'Finish: Obsidian black',
      'Weight: 28g',
      `Engraving: ${displayEngraving}`,
      'Price: £285 including personalisation',
      '',
      'Review only. No payment or reservation has been processed.',
      'This summary is not an order or reservation confirmation.',
      '',
    ].join('\n');
    let objectUrl;
    let link;

    try {
      const file = new Blob(['\uFEFF', summary], { type: 'text/plain;charset=utf-8' });
      objectUrl = window.URL.createObjectURL(file);
      link = document.createElement('a');
      link.href = objectUrl;
      link.download = 'vale-obsidian-no-01-selection.txt';
      link.hidden = true;
      document.body.appendChild(link);
      link.click();
      setDownloadMessage('Your browser has been asked to download your selection. No reservation has been placed.');
    } catch {
      setDownloadMessage('A download could not be started in this browser. You can copy the selection details above for your records. No reservation has been placed.');
    } finally {
      link?.remove();
      // Give the browser time to consume the file before releasing its URL.
      if (objectUrl) window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1000);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      titleId={titleId}
      descriptionId={descriptionId}
      className="reservation-dialog"
    >
      <p className="eyebrow">Valé / Selection review</p>
      <h2 className="dialog-title" id={titleId}>A considered <em>choice.</em></h2>
      <p className="dialog-description" id={descriptionId}>
        Review your Obsidian No. 01 and the mark that makes it yours. This is a review only, not a reservation.
      </p>

      <dl className="selection-summary">
        <div className="selection-row">
          <dt>The pen</dt>
          <dd>Obsidian No. 01</dd>
        </div>
        <div className="selection-row">
          <dt>Edition</dt>
          <dd>01 / 250</dd>
        </div>
        <div className="selection-row">
          <dt>Finish</dt>
          <dd>Obsidian black</dd>
        </div>
        <div className="selection-row">
          <dt>Weight</dt>
          <dd>28g</dd>
        </div>
        <div className="selection-row">
          <dt>Engraving</dt>
          <dd>
            <bdi>{displayEngraving}</bdi>{' '}
            <button
              className="text-button"
              type="button"
              onClick={() => {
                onClose();
                onEdit();
              }}
            >
              Edit engraving
            </button>
          </dd>
        </div>
      </dl>

      <p className="selection-price"><span>£285</span><small>including personalisation</small></p>
      <p className="dialog-notice">
        No payment or reservation is processed here. Saving keeps your selection in this browser on this device only.
      </p>

      {/* Keep this live region and the initiating button mounted: saving never
          removes or disables the focused control, or moves focus unexpectedly. */}
      <div className="saved-selection" role="status" aria-live="polite" aria-atomic="true">
        {saveMessage && <p>{saveMessage}</p>}
        {downloadMessage && <p>{downloadMessage}</p>}
      </div>

      <div className="dialog-actions">
        <button className="button button--dark" type="button" onClick={saveSelection}>
          <span>Save your selection</span><span className="arrow" aria-hidden="true">↗</span>
        </button>
        <button className="text-button" type="button" onClick={downloadSelection}>
          Download selection (.txt)
        </button>
      </div>
    </Modal>
  );
}

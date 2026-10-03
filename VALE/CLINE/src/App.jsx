import { useRef, useState } from 'react';
import Header, { Wordmark } from './components/Header.jsx';
import Pen from './components/Pen.jsx';
import Modal from './components/Modal.jsx';
import ReservationDialog from './components/ReservationDialog.jsx';
import { Arrow, Button, SectionLabel, TextLink } from './components/UI.jsx';
import { ValeMark } from './components/ValeLogo.jsx';
import useReveal from './hooks/useReveal.js';

const features = [
  { title: 'Perfectly weighted.', label: 'The balance', metric: '28', unit: 'g', description: '28 grams, balanced at the point where thumb meets forefinger. It disappears into the hand.', detail: 'Substantial enough to feel present. Quiet enough to become instinctive.', view: 'full', caption: 'Balance, by design' },
  { title: 'Hand-finished.', label: 'The craft', metric: '17', unit: 'components', description: 'Seventeen individual components, assembled and polished by one artisan in our London atelier.', detail: 'Every surface is considered by hand. Every detail earns its place.', view: 'finish', caption: 'A closer look at the finish' },
  { title: 'Endlessly refillable.', label: 'The ritual', metric: '800', unit: 'm', description: 'A lifetime object, not a disposable one. Our black Schmidt® refill glides for 800 metres.', detail: 'Keep the object. Change the refill. The ritual remains yours.', view: 'nib', caption: 'Made to write. Made to stay.' },
];

function Hero() {
  const scene = useRef(null);
  const inspect = (event) => {
    if (event.pointerType !== 'mouse' || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    scene.current?.style.setProperty('--inspect-x', `${((event.clientX - bounds.left) / bounds.width - .5) * 8}deg`);
    scene.current?.style.setProperty('--inspect-y', `${((event.clientY - bounds.top) / bounds.height - .5) * -6}deg`);
  };
  const reset = () => { scene.current?.style.setProperty('--inspect-x', '0deg'); scene.current?.style.setProperty('--inspect-y', '0deg'); };

  return <section className="hero" id="pen" aria-labelledby="hero-title" tabIndex={-1}>
    <div className="hero-ambient" aria-hidden="true" />
    <div className="shell hero-layout">
      <div className="hero-heading">
        <p className="eyebrow hero-eyebrow"><span />The Obsidian No. 01</p>
        <h1 id="hero-title">Make your<br /><em>mark.</em></h1>
      </div>
      <figure className="hero-product" onPointerMove={inspect} onPointerLeave={reset}>
        <span className="hero-edition-ghost" aria-hidden="true">01</span>
        <div className="hero-product-scene" ref={scene}><Pen /></div>
        <figcaption className="hero-product-caption"><span className="caption-rule" /><span>Obsidian black<br /><small>Precision, in its quietest form.</small></span></figcaption>
        <span className="hero-product-index" aria-hidden="true">VALÉ / LONDON</span>
      </figure>
      <div className="hero-intro">
        <p>A precision writing instrument.<br />For those who choose restraint, not noise.</p>
        <div className="hero-actions"><Button href="#craft">Discover the pen</Button><TextLink href="#personalise">Make it yours</TextLink></div>
      </div>
      <div className="hero-bottom">
        <a className="scroll-cue" href="#atelier"><Arrow direction="down" /><span>A study in restraint</span></a>
        <dl className="hero-specs"><div><dt>Balanced weight</dt><dd>28<span>g</span></dd></div><div><dt>Individual components</dt><dd>17</dd></div><div><dt>Writing distance</dt><dd>800<span>m</span></dd></div></dl>
        <span className="hero-edition caption">Edition 01 / 250</span>
      </div>
    </div>
  </section>;
}

function Philosophy() {
  return <section className="philosophy light-section" id="atelier" aria-labelledby="philosophy-title" tabIndex={-1}>
    <div className="shell">
      <SectionLabel number="01">The philosophy</SectionLabel>
      <div className="philosophy-layout">
        <h2 className="display" id="philosophy-title" data-reveal>Nothing extra.<br /><em>Everything</em><br />essential.</h2>
        <div className="philosophy-copy" data-reveal>
          <ValeMark className="philosophy-mark" />
          <p>In an age of noise, the most confident objects know when to be quiet.</p>
          <p>Obsidian No. 01 brings the discipline of coachbuilt design to the everyday ritual of writing — weight, balance and tactile pleasure, refined to a single line.</p>
          <span className="editorial-signature">Made for the considered life.</span>
          <span className="caption philosophy-signoff">VALÉ / LONDON</span>
        </div>
      </div>
    </div>
  </section>;
}

function Engineering() {
  const [active, setActive] = useState(0);
  const tabs = useRef([]);
  const feature = features[active];
  const onKeyDown = (event, index) => {
    let next;
    if (['ArrowDown', 'ArrowRight'].includes(event.key)) next = (index + 1) % features.length;
    if (['ArrowUp', 'ArrowLeft'].includes(event.key)) next = (index + features.length - 1) % features.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = features.length - 1;
    if (next === undefined) return;
    event.preventDefault(); setActive(next); tabs.current[next]?.focus();
  };

  return <section className="engineering" id="craft" aria-labelledby="engineering-title" tabIndex={-1}>
    <div className="shell">
      <SectionLabel number="02">The engineering</SectionLabel>
      <div className="section-heading" data-reveal><h2 className="display" id="engineering-title">Built to be<br /><em>remembered.</em></h2><p>Every detail earns its place.<br />This is precision you can feel<br className="desktop-break" /> before you see it.</p></div>
      <div className="engineering-layout" data-reveal>
        <div className="engineering-controls">
          <p className="caption interaction-hint">Three principles. Nothing more.</p>
          <div className="feature-tabs" role="tablist" aria-label="Explore the engineering" aria-orientation="vertical">
            {features.map((item, index) => <button className={`feature-tab${index === active ? ' is-active' : ''}`} id={`feature-tab-${index}`} key={item.title} ref={(element) => { tabs.current[index] = element; }} role="tab" type="button" aria-selected={index === active} aria-controls={`feature-panel-${index}`} tabIndex={index === active ? 0 : -1} onClick={() => setActive(index)} onKeyDown={(event) => onKeyDown(event, index)}>
              <span className="feature-number">0{index + 1}</span><span className="feature-tab-title">{item.title}</span><span className="feature-indicator" aria-hidden="true">{index === active ? '−' : '+'}</span>
            </button>)}
          </div>
          <div className="feature-text" key={active}><p>{feature.description}</p><span>{feature.detail}</span></div>
          <a className="text-link" href="#details"><span>The finer details</span><Arrow /></a>
        </div>
        <div className="engineering-visuals">
          {features.map((item, index) => <div key={item.title} id={`feature-panel-${index}`} className={`engineering-panel engineering-panel--${index}`} role="tabpanel" tabIndex={0} aria-labelledby={`feature-tab-${index}`} hidden={index !== active}>
            <div className="engineering-panel-top"><span className="caption">{item.label}</span><span className="caption">0{index + 1} / 03</span></div>
            <div className="engineering-pen"><Pen view={item.view} /></div>
            {index === 0 && <div className="balance-indicator" aria-hidden="true"><i /><span>Point of balance</span></div>}
            <div className="engineering-panel-bottom"><div className="engineering-metric">{item.metric}<span>{item.unit}</span></div><span className="engineering-caption caption">{item.caption}</span></div>
          </div>)}
        </div>
      </div>
    </div>
  </section>;
}

function Details() {
  return <section className="details light-section" id="details" aria-labelledby="details-title" tabIndex={-1}>
    <div className="shell">
      <div className="details-heading" data-reveal><div><p className="eyebrow">The object in detail</p><h2 id="details-title">Closer to <em>the hand.</em></h2></div><p>Nothing is added for effect.<br />Everything is there for a reason.</p></div>
      <dl className="detail-specs" data-reveal>
        <div><dt><span>01</span>The material</dt><dd>Obsidian black<small>A dark, tactile presence.<br />Warm metallic accents.</small></dd></div>
        <div><dt><span>02</span>The balance</dt><dd>28<span className="unit">g</span><small>Balanced where thumb<br />meets forefinger.</small></dd></div>
        <div><dt><span>03</span>The craft</dt><dd>17 components<small>Assembled and polished<br />in our London atelier.</small></dd></div>
        <div><dt><span>04</span>The refill</dt><dd>800<span className="unit">m</span><small>A black Schmidt® refill.<br />Used. Refilled. Kept.</small></dd></div>
      </dl>
    </div>
  </section>;
}

function Personalisation({ engraving, setEngraving, onConfirm, confirmed }) {
  const [view, setView] = useState('engraving');
  const count = engraving.length;
  const input = useRef(null);
  const examples = ['E. W.', '01.06.2026', 'YOURS, ALWAYS'];
  const submit = (event) => {
    event.preventDefault();
    if (!engraving.trim()) { input.current?.focus(); return; }
    onConfirm();
    document.getElementById('reserve')?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
    document.getElementById('reserve-title')?.focus({ preventScroll: true });
  };
  return <section className="personalise" id="personalise" aria-labelledby="personalise-title" tabIndex={-1}>
    <div className="shell">
      <SectionLabel number="03">A personal expression</SectionLabel>
      <div className="personalise-layout">
        <div className="personalise-copy" data-reveal>
          <h2 className="display" id="personalise-title">Yours,<br /><em>by design.</em></h2>
          <p>A name. A date. A few words worth carrying.<br className="desktop-break" /> A small detail that makes it entirely yours.</p>
          <form className="engraving-form" onSubmit={submit}>
            <div className="engraving-label"><label htmlFor="engraving">Engrave your mark</label><span className="caption" aria-hidden="true">{String(count).padStart(2, '0')} / 16</span></div>
            <div className="engraving-input-wrap"><input id="engraving" ref={input} name="engraving" value={engraving} onChange={(event) => setEngraving(event.target.value.toUpperCase().slice(0, 16))} maxLength={16} placeholder="YOUR MARK" autoComplete="off" spellCheck={false} aria-describedby="engraving-help" />{engraving ? <button className="clear-engraving" type="button" aria-label="Clear engraving" onClick={() => { setEngraving(''); input.current?.focus(); }}>×</button> : <span className="input-caret" aria-hidden="true"><Arrow direction="right" /></span>}</div>
            <p className="engraving-help" id="engraving-help">Up to 16 characters. Personalisation included.</p>
            <div className="engraving-examples"><span>Try a mark</span>{examples.map((example) => <button type="button" key={example} aria-pressed={engraving === example} onClick={() => { setEngraving(example); input.current?.focus(); }}>{example}</button>)}</div>
            <Button className="button--outline" type="submit" disabled={!engraving.trim()}>{confirmed && engraving.trim() ? 'Mark selected' : 'Choose this engraving'}</Button>
            <p className="preview-disclaimer">Illustrative preview. Final appearance may vary.</p>
          </form>
        </div>
        <div className={`engraving-stage engraving-stage--${view}`} data-reveal>
          <div className="engraving-stage-top"><span className="caption">Obsidian / 01</span><span className="live-preview"><i aria-hidden="true" />Live preview</span></div>
          <div className="engraving-art"><Pen engraving={engraving.trim() || 'YOUR MARK'} view={view} /></div>
          <div className="engraving-registration" aria-hidden="true"><span />{view === 'engraving' ? 'Your words. Always with you.' : 'The complete instrument.'}</div>
          <div className="engraving-stage-bottom"><span className="caption">Your mark, considered.</span><div className="preview-toggle" role="group" aria-label="Engraving preview view"><button type="button" aria-pressed={view === 'engraving'} onClick={() => setView('engraving')}>Detail</button><button type="button" aria-pressed={view === 'full'} onClick={() => setView('full')}>Full pen</button></div></div>
          <span className="sr-only" role="status">{engraving.trim() ? `Preview engraving: ${engraving.trim()}` : 'Enter your engraving to preview it on the pen.'}</span>
        </div>
      </div>
    </div>
  </section>;
}

function Reservation({ engraving, confirmed, onReserve }) {
  return <section className="reservation light-section" id="reserve" aria-labelledby="reserve-title" tabIndex={-1}>
    <div className="shell">
      <SectionLabel number="04">The first edition</SectionLabel>
      <div className="reservation-layout">
        <div className="reservation-product" data-reveal>
          <span className="reservation-word" aria-hidden="true">Obsidian</span>
          <div className="reservation-pen"><Pen engraving={engraving.trim() || 'VALÉ / 01'} /></div>
          <span className="reservation-product-caption caption">The Obsidian No. 01 / VALÉ London</span>
        </div>
        <div className="reservation-copy" data-reveal>
          <p className="eyebrow">Obsidian / 01</p>
          <h2 id="reserve-title" tabIndex={-1}>Leave an<br /><em>impression.</em></h2>
          <p>Presented in a hand-wrapped case.<br />Ready to become part of your story.</p>
          <div className="reservation-selection"><span className="caption">Your engraving</span><span className={engraving.trim() ? 'selected-engraving' : ''}>{engraving.trim() || 'Make it personal'}</span><a href="#personalise" aria-label={engraving.trim() ? 'Edit your engraving' : 'Add your engraving'}>{engraving.trim() ? 'Edit' : 'Add'}<Arrow /></a></div>
          {confirmed && engraving.trim() && <span className="sr-only" role="status">Your engraving has been selected.</span>}
          <div className="reservation-price"><span>£285</span><span className="caption">Including<br />personalisation</span></div>
          <Button className="button--dark" onClick={onReserve}>Reserve your Obsidian</Button>
          <div className="reservation-assurance"><span>Personalisation included</span><span>Lifetime service</span></div>
          <p className="reservation-disclaimer">Explore your selection. No payment or reservation is processed in this preview.</p>
        </div>
      </div>
    </div>
  </section>;
}

function Footer({ onInfo }) {
  return <footer className="site-footer">
    <div className="shell">
      <div className="footer-main"><div><Wordmark /><span className="footer-london caption">London</span></div><p>For those who leave<br /><em>an impression.</em></p><nav className="footer-nav" aria-label="Footer navigation"><a href="#atelier">The atelier</a><a href="#craft">The pen</a><a href="#personalise">Personalise</a><button type="button" onClick={() => onInfo('care')}>Care guide</button><button type="button" onClick={() => onInfo('contact')}>Contact</button></nav></div>
      <div className="footer-bottom"><span>© {new Date().getFullYear()} VALÉ London</span><span>Designed with intent. Made to be kept.</span><a href="#top">Back to the beginning<Arrow direction="down" /></a></div>
    </div>
  </footer>;
}

function App() {
  const root = useRef(null);
  const [engraving, setEngraving] = useState(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem('vale-selection'));
      return saved?.product === 'Obsidian No. 01' && typeof saved.engraving === 'string'
        ? saved.engraving.toUpperCase().slice(0, 16) : '';
    } catch { return ''; }
  });
  const [confirmed, setConfirmed] = useState(false);
  const [reservationOpen, setReservationOpen] = useState(false);
  const [info, setInfo] = useState(null);
  useReveal(root);
  const updateEngraving = (value) => { setEngraving(value); setConfirmed(false); };
  const editEngraving = () => requestAnimationFrame(() => {
    document.getElementById('personalise')?.scrollIntoView({ behavior: 'instant' });
    document.getElementById('engraving')?.focus({ preventScroll: true });
  });

  return <div className="app-shell" id="top" ref={root}>
    <Header />
    <main id="main" tabIndex={-1}>
      <Hero />
      <Philosophy />
      <Engineering />
      <Details />
      <Personalisation engraving={engraving} setEngraving={updateEngraving} onConfirm={() => setConfirmed(true)} confirmed={confirmed} />
      <Reservation engraving={engraving} confirmed={confirmed} onReserve={() => setReservationOpen(true)} />
    </main>
    <Footer onInfo={setInfo} />
    <ReservationDialog open={reservationOpen} onClose={() => setReservationOpen(false)} engraving={engraving.trim()} onEdit={editEngraving} />
    <Modal open={Boolean(info)} onClose={() => setInfo(null)} titleId="information-title" className="information-dialog">
      <p className="eyebrow">VALÉ / The considered life</p>
      <h2 className="dialog-title" id="information-title">{info === 'care' ? 'Made to be kept.' : 'The atelier.'}</h2>
      {info === 'care' ? <div className="care-content"><p>A little attention, for an everyday companion.</p><h3>Care for the finish</h3><p>Gently wipe with a soft, dry cloth. Avoid abrasive cleaners and keep your pen in its presentation case when not in use.</p><h3>Keep the ritual</h3><p>Obsidian No. 01 is refillable, with a black Schmidt® refill. Check the correct replacement and fitting instructions before changing a refill.</p><h3>A lasting relationship</h3><p>Lifetime service is part of the Obsidian story. Service enquiries are not connected in this website preview.</p></div> : <div className="care-content"><p>For questions about your Obsidian, personalisation or care.</p><p className="dialog-notice">This website is a product preview. An atelier enquiry service is not connected, and no messages or personal details are collected here.</p><Button className="button--dark" onClick={() => { setInfo(null); setReservationOpen(true); }}>Explore your selection</Button></div>}
    </Modal>
  </div>;
}

export default App;

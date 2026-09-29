import { useEffect, useRef, useState } from 'react';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { ValeMark } from './components/ValeLogo.jsx';

gsap.registerPlugin(ScrollTrigger);

const features = [
  {
    number: '01 / 03',
    title: 'Perfectly weighted',
    description: '28 grams, balanced at the point where thumb meets forefinger. It disappears into the hand.',
    detail: 'The balance is deliberate: substantial enough to feel present, quiet enough to become instinctive.',
    icon: 'balance',
  },
  {
    number: '02 / 03',
    title: 'Hand-finished',
    description: 'Seventeen individual components, assembled and polished by one artisan in our London atelier.',
    detail: 'Every surface is considered by hand, leaving only the details that earn their place.',
    icon: 'craft',
  },
  {
    number: '03 / 03',
    title: 'Endlessly refillable',
    description: 'A lifetime object, not a disposable one. Our black Schmidt® refill glides for 800 metres.',
    detail: 'Keep the object. Change the refill. The ritual remains yours for as long as you choose it.',
    icon: 'refill',
  },
];

const discoveryItems = [
  { label: 'The material', value: 'Obsidian black', detail: 'A dark, tactile presence with warm metallic accents.' },
  { label: 'The balance', value: '28g', detail: 'Balanced around the point where thumb meets forefinger.' },
  { label: 'The craft', value: '17 components', detail: 'Assembled and polished by one artisan in our London atelier.' },
  { label: 'The refill', value: '800m', detail: 'A black Schmidt® refill designed to glide, then be replaced.' },
];

function Wordmark() {
  return (
    <a className="wordmark" href="#top" aria-label="Valé home">
      <ValeMark />
      <span>VALÉ</span>
    </a>
  );
}

function TextLink({ children, href = '#reserve', className = '' }) {
  return <a className={`text-link ${className}`.trim()} href={href}>{children}</a>;
}

function Button({ children, onClick, href, type = 'button', className = '', ...props }) {
  const classes = `button ${className}`.trim();
  const content = <><span>{children}</span><span className="arrow" aria-hidden="true">↗</span></>;
  return href
    ? <a className={classes} href={href} {...props}>{content}</a>
    : <button className={classes} type={type} onClick={onClick} {...props}>{content}</button>;
}

function Pen({ sceneRef, idPrefix = 'hero-pen', engraving = 'VALÉ / 01', className = '' }) {
  const id = (name) => `${idPrefix}-${name}`;
  const paint = (name) => `url(#${id(name)})`;
  const sceneClass = ['pen-scene', className].filter(Boolean).join(' ');

  return (
    <div className={sceneClass} ref={sceneRef}>
      <svg className="pen-render" viewBox="0 0 760 300" role="img" aria-labelledby={`${idPrefix}-title ${idPrefix}-description`}>
        <title id={`${idPrefix}-title`}>Obsidian No. 01 fountain pen</title>
        <desc id={`${idPrefix}-description`}>A faceted black lacquer fountain pen with a warm gold nib and clip.</desc>
        <defs>
          <linearGradient id={id('body')} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#11110f" />
            <stop offset=".12" stopColor="#3b382f" />
            <stop offset=".2" stopColor="#0a0b0a" />
            <stop offset=".43" stopColor="#494437" />
            <stop offset=".5" stopColor="#171815" />
            <stop offset=".72" stopColor="#090a09" />
            <stop offset=".9" stopColor="#554a38" />
            <stop offset="1" stopColor="#11110f" />
          </linearGradient>
          <linearGradient id={id('top-plane')} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#686153" stopOpacity=".78" />
            <stop offset=".35" stopColor="#2e2c26" stopOpacity=".72" />
            <stop offset="1" stopColor="#10110f" stopOpacity=".1" />
          </linearGradient>
          <linearGradient id={id('bottom-plane')} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#0b0c0b" stopOpacity=".12" />
            <stop offset="1" stopColor="#020302" stopOpacity=".9" />
          </linearGradient>
          <linearGradient id={id('metal')} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#60451f" />
            <stop offset=".18" stopColor="#c8954c" />
            <stop offset=".4" stopColor="#f2cf86" />
            <stop offset=".57" stopColor="#8d622d" />
            <stop offset=".8" stopColor="#e5ba70" />
            <stop offset="1" stopColor="#5d411d" />
          </linearGradient>
          <linearGradient id={id('nib')} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#f2d18f" />
            <stop offset=".42" stopColor="#a97837" />
            <stop offset=".56" stopColor="#f0c87b" />
            <stop offset="1" stopColor="#6f4b22" />
          </linearGradient>
          <linearGradient id={id('cap')} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#302e28" />
            <stop offset=".2" stopColor="#0c0e0d" />
            <stop offset=".52" stopColor="#4f4a3e" />
            <stop offset=".68" stopColor="#111311" />
            <stop offset=".92" stopColor="#36352d" />
            <stop offset="1" stopColor="#11120f" />
          </linearGradient>
          <filter id={id('shadow')} x="-20%" y="-30%" width="150%" height="180%">
            <feDropShadow dx="0" dy="11" stdDeviation="8" floodColor="#000000" floodOpacity=".58" />
          </filter>
          <filter id={id('glow')} x="-20%" y="-100%" width="140%" height="300%">
            <feGaussianBlur stdDeviation="2.5" />
          </filter>
        </defs>
        <g className="pen-art" filter={paint('shadow')}>
          <path d="M142 113c-17 4-29 16-29 37s12 33 29 37l18-10v-54Z" fill={paint('metal')} />
          <path d="M137 117c9-5 19-7 33-7h27v80h-27c-14 0-24-2-33-7 7-17 7-49 0-66Z" fill="#191a17" />
          <path d="M153 112h25v76h-25c6-17 6-59 0-76Z" fill={paint('top-plane')} />
          <path d="m146 138-93 12 93 12c12-5 12-19 0-24Z" fill="#11120f" stroke="#6c4c26" strokeWidth="1.5" />
          <path d="m151 123-119 27 119 27 30-14v-26Z" fill={paint('nib')} stroke="#6c4b22" strokeWidth="1.25" />
          <path d="m151 123-119 27 119-5 30-8v-14Z" fill="#f7d99c" opacity=".24" />
          <path d="M151 150 43 150" fill="none" stroke="#3a2714" strokeWidth="2" />
          <circle cx="129" cy="150" r="5" fill="#53391d" stroke="#e4b96f" strokeWidth="1.2" />
          <circle cx="129" cy="149" r="1.2" fill="#f9dda2" />
          <path d="M45 150 31 150" fill="none" stroke="#1f1710" strokeWidth="2.5" strokeLinecap="round" />
          <path d="M174 106c10-4 21-6 35-6h372c16 0 26 10 26 24v52c0 14-10 24-26 24H209c-14 0-25-2-35-6 7-18 7-70 0-88Z" fill={paint('body')} />
          <path d="M184 108c13-5 26-7 41-7h356c13 0 23 8 24 20H203c-9 0-15-4-19-13Z" fill={paint('top-plane')} />
          <path d="M184 192c13 5 26 7 41 7h356c13 0 23-8 24-20H203c-9 0-15 4-19 13Z" fill={paint('bottom-plane')} />
          <path d="M216 112h326c16 0 26 3 35 10H216c-11 0-18-2-24-6 7-3 14-4 24-4Z" fill="#b9a77f" opacity=".12" />
          <path d="M205 118c100 5 232 3 354-2" fill="none" stroke="#e8d39d" strokeWidth="2" opacity=".25" filter={paint('glow')} />
          <path d="M203 177c122 7 240 5 355-1" fill="none" stroke="#000" strokeWidth="4" opacity=".45" />
          <path d="M202 134h376" fill="none" stroke="#dfc489" strokeWidth="1" opacity=".24" />
          <path d="M202 168h376" fill="none" stroke="#050605" strokeWidth="1.5" opacity=".75" />
          <text x="342" y="157" fill="#d7b373" opacity=".74" fontSize="9" fontFamily="Arial, sans-serif" fontWeight="700" letterSpacing="4">{engraving.trim().toUpperCase() || 'VALÉ / 01'}</text>
          <path d="M574 101h20c10 0 17 8 17 18v62c0 10-7 18-17 18h-20Z" fill={paint('metal')} stroke="#4c351b" strokeWidth="1.5" />
          <path d="M583 105h10c7 0 11 7 11 14v62c0 7-4 14-11 14h-10Z" fill="#f2cb82" opacity=".26" />
          <path d="M610 104h31c31 0 56 19 56 46s-25 46-56 46h-31c8-26 8-66 0-92Z" fill={paint('cap')} />
          <path d="M622 108c17 1 27 7 36 14 8 7 13 16 13 28s-5 21-13 28c-9 7-19 13-36 14 9-22 9-62 0-84Z" fill="#77705f" opacity=".17" />
          <path d="M637 110c21-1 42 8 53 22" fill="none" stroke="#d9c99f" strokeWidth="2" opacity=".22" />
          <path d="M641 110c28 2 49 16 51 37 2 22-18 39-51 43" fill="none" stroke="#050605" strokeWidth="2" opacity=".75" />
          <path d="M630 111c26-12 50-2 53 17 2 14-9 22-21 22h-17" fill="none" stroke={paint('metal')} strokeWidth="5" strokeLinecap="round" />
          <circle cx="630" cy="112" r="6" fill={paint('metal')} stroke="#58401f" strokeWidth="1.5" />
          <circle cx="630" cy="112" r="2" fill="#f5d899" />
          <path d="M677 142c5 3 8 8 8 13s-3 10-8 13" fill="none" stroke="#dcb977" strokeWidth="1.5" opacity=".55" />
        </g>
      </svg>
    </div>
  );
}

function FeatureGlyph({ type }) {
  return <span className={`feature-glyph feature-glyph--${type}`} aria-hidden="true"><i /></span>;
}

function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [headerScrolled, setHeaderScrolled] = useState(false);
  const [activeSection, setActiveSection] = useState('pen');
  const [activeFeature, setActiveFeature] = useState(0);
  const [engraving, setEngraving] = useState('');
  const [toast, setToast] = useState('');
  const pageRef = useRef(null);
  const sceneRef = useRef(null);
  const stageRef = useRef(null);
  const toastTimer = useRef(null);

  useEffect(() => {
    const handleScroll = () => setHeaderScrolled(window.scrollY > 36);
    handleScroll();
    window.addEventListener('scroll', handleScroll, { passive: true });

    const sectionIds = ['pen', 'atelier', 'craft', 'details', 'personalise', 'reserve'];
    const sections = sectionIds.map((id) => document.getElementById(id)).filter(Boolean);
    const observer = 'IntersectionObserver' in window
      ? new IntersectionObserver((entries) => {
        const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible[0]) setActiveSection(visible[0].target.id);
      }, { rootMargin: '-25% 0px -60% 0px', threshold: [0, .2, .5, .8] })
      : null;
    sections.forEach((section) => observer?.observe(section));

    return () => {
      window.removeEventListener('scroll', handleScroll);
      observer?.disconnect();
    };
  }, []);

  useEffect(() => {
    if (!menuOpen) return undefined;
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setMenuOpen(false);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [menuOpen]);

  useEffect(() => () => window.clearTimeout(toastTimer.current), []);

  useEffect(() => {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let removeStageListeners = () => {};
    const context = gsap.context(() => {
      if (reduceMotion) return;

      gsap.fromTo('[data-hero]', { autoAlpha: 0, y: 22 }, { autoAlpha: 1, y: 0, duration: .85, stagger: .1, ease: 'power3.out', delay: .1 });
      gsap.fromTo(sceneRef.current, { autoAlpha: 0, x: 72, rotation: -12 }, { autoAlpha: 1, x: 0, rotation: -18, duration: 1.5, ease: 'expo.out', delay: .35 });
      gsap.to(sceneRef.current, { y: -10, duration: 3.8, ease: 'sine.inOut', repeat: -1, yoyo: true, delay: 1.9 });

      const stage = stageRef.current;
      if (stage && window.matchMedia('(pointer: fine)').matches) {
        const handleMove = (event) => {
          const bounds = stage.getBoundingClientRect();
          const x = (event.clientX - bounds.left) / bounds.width - .5;
          const y = (event.clientY - bounds.top) / bounds.height - .5;
          gsap.to(sceneRef.current, { rotationY: -14 + x * 8, rotationX: y * -4, duration: .7, ease: 'power3.out', overwrite: 'auto' });
        };
        const handleLeave = () => gsap.to(sceneRef.current, { rotationY: -14, rotationX: 0, duration: .9, ease: 'power3.out' });
        stage.addEventListener('pointermove', handleMove);
        stage.addEventListener('pointerleave', handleLeave);
        removeStageListeners = () => {
          stage.removeEventListener('pointermove', handleMove);
          stage.removeEventListener('pointerleave', handleLeave);
        };
      }

      gsap.utils.toArray('[data-reveal]').forEach((element) => {
        gsap.fromTo(element, { autoAlpha: 0, y: 34 }, { autoAlpha: 1, y: 0, duration: .9, ease: 'power3.out', scrollTrigger: { trigger: element, start: 'top 84%', once: true } });
      });
    }, pageRef);

    return () => {
      removeStageListeners();
      context.revert();
    };
  }, []);

  const announce = (message) => {
    setToast(message);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(''), 5200);
  };

  const closeMenu = () => setMenuOpen(false);
  const previewEngraving = (event) => {
    event.preventDefault();
    announce('Engraving preview updated. Demo only — no reservation has been placed.');
  };
  const requestReservation = () => announce('Private viewing prepared. Demo only — no reservation has been placed.');
  const displayEngraving = engraving.trim() || 'YOUR MARK';
  const currentFeature = features[activeFeature];

  return (
    <div className="app-shell" ref={pageRef}>
      <header className={`site-header${headerScrolled ? ' is-scrolled' : ''}`}>
        <div className="shell nav">
          <Wordmark />
          <nav id="main-nav" className={`nav-links${menuOpen ? ' is-open' : ''}`} aria-label="Main navigation">
            <a className={activeSection === 'atelier' ? 'is-active' : ''} href="#atelier" aria-current={activeSection === 'atelier' ? 'page' : undefined} onClick={closeMenu}>The atelier</a>
            <a className={activeSection === 'pen' ? 'is-active' : ''} href="#pen" aria-current={activeSection === 'pen' ? 'page' : undefined} onClick={closeMenu}>The pen</a>
            <a className={activeSection === 'personalise' ? 'is-active' : ''} href="#personalise" aria-current={activeSection === 'personalise' ? 'page' : undefined} onClick={closeMenu}>Personalise</a>
          </nav>
          <div className="nav-actions">
            <span className="nav-edition">Edition 01 / 250</span>
            <TextLink href="#reserve" className="nav-reserve">Reserve yours</TextLink>
            <button className="menu-button" type="button" aria-controls="main-nav" aria-label={menuOpen ? 'Close menu' : 'Open menu'} aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}>
              <span aria-hidden="true">{menuOpen ? '×' : '☰'}</span>
            </button>
          </div>
        </div>
      </header>

      <main id="top">
        <section className="hero" id="pen" aria-labelledby="hero-title">
          <div className="hero-halo" aria-hidden="true" />
          <div className="shell hero-grid">
            <div className="hero-copy">
              <div className="eyebrow hero-eyebrow" data-hero>The Obsidian No. 01</div>
              <h1 className="hero-title" id="hero-title" data-hero>Make your<br /><em>mark.</em></h1>
              <p className="hero-description" data-hero>A precision writing instrument, composed like a grand touring automobile. For the kind of owner who chooses restraint, not noise.</p>
              <div className="button-row" data-hero>
                <Button href="#details">Discover the pen</Button>
                <TextLink href="#atelier">Explore the atelier</TextLink>
              </div>
              <div className="hero-meta" data-hero>
                <div><strong>01</strong><span>Limited edition</span></div>
                <div><strong>∞</strong><span>Lifetime service</span></div>
                <div><strong>28g</strong><span>Balanced weight</span></div>
              </div>
            </div>
            <div className="product-stage" ref={stageRef} aria-label="Interactive render of the Obsidian No. 01 pen">
              <div className="product-stage-label" aria-hidden="true"><span>01</span><span>Obsidian / London</span></div>
              <div className="product-shadow" aria-hidden="true" />
              <div className="product-light product-light--one" aria-hidden="true" />
              <div className="product-light product-light--two" aria-hidden="true" />
              <Pen sceneRef={sceneRef} idPrefix="hero-pen" />
              <div className="product-stage-caption"><span>Move to inspect</span><span className="caption-line" /></div>
            </div>
          </div>
          <a className="scroll-cue" href="#atelier"><span>Scroll to explore</span><i aria-hidden="true" /></a>
        </section>

        <section className="statement" id="atelier" aria-labelledby="statement-title">
          <div className="statement-mark" aria-hidden="true">V</div>
          <div className="shell statement-grid">
            <div data-reveal>
              <div className="eyebrow">A study in restraint</div>
              <h2 id="statement-title">Nothing<br />extra.<br /><em>Everything</em><br />essential.</h2>
            </div>
            <div className="statement-copy" data-reveal>
              <p>In an age of noise, the most confident objects know when to be quiet. Obsidian No. 01 brings the discipline of coachbuilt design to the everyday ritual of writing — weight, balance and tactile pleasure, refined to a single line.</p>
              <div className="signature">Made for the considered life.<small>Valé London / Since 2024</small></div>
              <div className="statement-rule" aria-hidden="true"><span>01</span><i /></div>
            </div>
          </div>
        </section>

        <section className="craft" id="craft" aria-labelledby="craft-title">
          <div className="shell">
            <div className="section-head" data-reveal>
              <div><div className="eyebrow">The engineering</div><h2 id="craft-title">Built to be<br />remembered.</h2></div>
              <p className="section-note">Every detail earns its place. Every surface rewards the hand. This is precision you can feel before you see it.</p>
            </div>
            <div className="feature-explorer" data-reveal>
              <div className="feature-list" role="tablist" aria-label="Engineering details">
                {features.map((feature, index) => (
                  <button
                    className={`feature-trigger${activeFeature === index ? ' is-active' : ''}`}
                    key={feature.number}
                    id={`feature-tab-${index}`}
                    type="button"
                    role="tab"
                    tabIndex={activeFeature === index ? 0 : -1}
                    aria-selected={activeFeature === index}
                    aria-controls="feature-detail"
                    onClick={() => setActiveFeature(index)}
                    onKeyDown={(event) => {
                      if (!['ArrowDown', 'ArrowRight', 'ArrowUp', 'ArrowLeft'].includes(event.key)) return;
                      event.preventDefault();
                      const offset = event.key === 'ArrowDown' || event.key === 'ArrowRight' ? 1 : -1;
                      const nextIndex = (index + offset + features.length) % features.length;
                      setActiveFeature(nextIndex);
                      window.requestAnimationFrame(() => document.getElementById(`feature-tab-${nextIndex}`)?.focus());
                    }}
                  >
                    <span className="feature-trigger-number">{feature.number}</span>
                    <span className="feature-trigger-copy"><FeatureGlyph type={feature.icon} /><span><strong>{feature.title}</strong><small>{feature.description}</small></span></span>
                    <span className="feature-trigger-arrow" aria-hidden="true">↗</span>
                  </button>
                ))}
              </div>
              <div className="feature-detail" id="feature-detail" role="tabpanel" aria-labelledby={`feature-tab-${activeFeature}`} aria-live="polite">
                <div className="detail-index">{currentFeature.number}</div>
                <FeatureGlyph type={currentFeature.icon} />
                <div className="feature-detail-copy"><div className="eyebrow">A considered detail</div><h3>{currentFeature.title}</h3><p>{currentFeature.detail}</p><span className="detail-underline" aria-hidden="true" /></div>
              </div>
            </div>
          </div>
        </section>

        <section className="discovery" id="details" aria-labelledby="discovery-title">
          <div className="shell discovery-grid">
            <div className="discovery-intro" data-reveal>
              <div className="eyebrow">The object in detail</div>
              <h2 id="discovery-title">Closer to<br /><em>the hand.</em></h2>
              <p>Nothing is added for effect. Each part of Obsidian No. 01 exists to make the daily ritual feel more considered.</p>
              <div className="discovery-index" aria-hidden="true"><span>02</span><i /></div>
            </div>
            <div className="discovery-list" data-reveal>
              {discoveryItems.map((item, index) => (
                <div className="discovery-item" key={item.label}>
                  <span className="discovery-number">0{index + 1}</span>
                  <div><div className="eyebrow">{item.label}</div><h3>{item.value}</h3><p>{item.detail}</p></div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="personalise" id="personalise" aria-labelledby="personalise-title">
          <div className="shell personalise-grid">
            <div className="personalise-visual" data-reveal>
              <div className="personalise-visual-label"><span>OBSIDIAN / 01</span><span>YOUR MARK</span></div>
              <div className="personalise-orbit" aria-hidden="true" />
              <Pen idPrefix="preview-pen" engraving={displayEngraving} className="pen-scene--preview" />
              <div className="personalise-note"><span>Live engraving preview</span><span className="caption-line" /></div>
            </div>
            <div className="personalise-copy" data-reveal>
              <div className="eyebrow">The first edition</div>
              <h2 id="personalise-title">Yours,<br /><em>by design.</em></h2>
              <p>Engrave a name, a date or the words worth carrying. See your mark on the Obsidian No. 01 before a private viewing.</p>
              <form className="engraving-form" onSubmit={previewEngraving}>
                <label htmlFor="engraving">Engrave your mark</label>
                <div className="engraving-input-wrap"><input id="engraving" name="engraving" value={engraving} onChange={(event) => setEngraving(event.target.value)} maxLength="16" placeholder="YOUR NAME / DATE" autoComplete="off" /><span>{engraving.length} / 16</span></div>
                <div className="form-foot"><span>Preview only</span><button className="form-submit" type="submit">Update preview <span aria-hidden="true">↗</span></button></div>
              </form>
              <div className="personalise-service"><span className="service-mark">∞</span><span><strong>Lifetime service</strong><small>A considered object, made to be kept.</small></span></div>
            </div>
          </div>
        </section>

        <section className="reservation" id="reserve" aria-labelledby="reserve-title">
          <div className="shell reservation-grid">
            <div data-reveal><div className="eyebrow">A private viewing</div><h2 id="reserve-title">Leave an<br /><em>impression.</em></h2><p>Obsidian No. 01 arrives in a hand-wrapped presentation case, ready to become part of your story.</p></div>
            <div className="reservation-panel" data-reveal>
              <div className="reservation-panel-top"><span>Edition 01 / 250</span><span>Obsidian No. 01</span></div>
              <div className="price">£285 <small>including personalisation</small></div>
              <Button onClick={requestReservation}>Reserve your Obsidian</Button>
              <p className="reservation-note">Front-end preview only. No payment or reservation is processed here.</p>
            </div>
          </div>
        </section>
      </main>

      <footer>
        <div className="shell">
          <div className="footer-top"><Wordmark /><p>For those who leave an impression.</p><div className="footer-links"><a href="#atelier">The atelier</a><a href="#pen">The pen</a><a href="#personalise">Personalise</a><a href="#craft">Care guide</a><a href="#reserve">Contact</a><a href="#top">Instagram</a></div></div>
          <hr className="rule" />
          <div className="footer-bottom"><span>© 2024 Valé London</span><span>Designed with intent / Made in England</span></div>
        </div>
      </footer>
      <div className={`toast${toast ? ' is-visible' : ''}`} role="status" aria-live="polite">{toast}</div>
    </div>
  );
}

export default App;

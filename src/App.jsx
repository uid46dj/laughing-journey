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
    icon: <div className="icon-orbit"><span className="icon-core" /></div>,
  },
  {
    number: '02 / 03',
    title: 'Hand-finished',
    description: 'Seventeen individual components, assembled and polished by one artisan in our London atelier.',
    icon: <div className="icon-stack" />,
  },
  {
    number: '03 / 03',
    title: 'Endlessly refillable',
    description: 'A lifetime object, not a disposable one. Our black Schmidt® refill glides for 800 metres.',
    icon: <div className="icon-line" />,
  },
];

function Wordmark() {
  return (
    <a className="wordmark" href="#top" aria-label="Vale home">
      <ValeMark />
      <span>VALÉ</span>
    </a>
  );
}

function TextLink({ children, href = '#edition' }) {
  return <a className="text-link" href={href}>{children}</a>;
}

function Button({ children, onClick, href }) {
  const content = <>{children} <span className="arrow">↗</span></>;
  return href ? <a className="button" href={href}>{content}</a> : <button className="button" type="button" onClick={onClick}>{content}</button>;
}

function Pen({ sceneRef }) {
  return (
    <div className="pen-scene" id="penScene" ref={sceneRef}>
      <svg className="pen-render" viewBox="0 0 760 300" role="img" aria-labelledby="pen-title pen-description">
        <title id="pen-title">Obsidian No. 01 fountain pen</title>
        <desc id="pen-description">A faceted black lacquer fountain pen with a warm gold nib and clip.</desc>
        <defs>
          <linearGradient id="pen-body" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#11110f" />
            <stop offset=".12" stopColor="#3b382f" />
            <stop offset=".2" stopColor="#0a0b0a" />
            <stop offset=".43" stopColor="#494437" />
            <stop offset=".5" stopColor="#171815" />
            <stop offset=".72" stopColor="#090a09" />
            <stop offset=".9" stopColor="#554a38" />
            <stop offset="1" stopColor="#11110f" />
          </linearGradient>
          <linearGradient id="pen-top-plane" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#686153" stopOpacity=".78" />
            <stop offset=".35" stopColor="#2e2c26" stopOpacity=".72" />
            <stop offset="1" stopColor="#10110f" stopOpacity=".1" />
          </linearGradient>
          <linearGradient id="pen-bottom-plane" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#0b0c0b" stopOpacity=".12" />
            <stop offset="1" stopColor="#020302" stopOpacity=".9" />
          </linearGradient>
          <linearGradient id="pen-metal" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#60451f" />
            <stop offset=".18" stopColor="#c8954c" />
            <stop offset=".4" stopColor="#f2cf86" />
            <stop offset=".57" stopColor="#8d622d" />
            <stop offset=".8" stopColor="#e5ba70" />
            <stop offset="1" stopColor="#5d411d" />
          </linearGradient>
          <linearGradient id="pen-nib" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#f2d18f" />
            <stop offset=".42" stopColor="#a97837" />
            <stop offset=".56" stopColor="#f0c87b" />
            <stop offset="1" stopColor="#6f4b22" />
          </linearGradient>
          <linearGradient id="pen-cap" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#302e28" />
            <stop offset=".2" stopColor="#0c0e0d" />
            <stop offset=".52" stopColor="#4f4a3e" />
            <stop offset=".68" stopColor="#111311" />
            <stop offset=".92" stopColor="#36352d" />
            <stop offset="1" stopColor="#11120f" />
          </linearGradient>
          <filter id="pen-shadow" x="-20%" y="-30%" width="150%" height="180%">
            <feDropShadow dx="0" dy="11" stdDeviation="8" floodColor="#000000" floodOpacity=".58" />
          </filter>
          <filter id="pen-glow" x="-20%" y="-100%" width="140%" height="300%">
            <feGaussianBlur stdDeviation="2.5" />
          </filter>
        </defs>
        <g className="pen-art" filter="url(#pen-shadow)">
          <path className="pen-rear-finial" d="M142 113c-17 4-29 16-29 37s12 33 29 37l18-10v-54Z" fill="url(#pen-metal)" />
          <path className="pen-grip" d="M137 117c9-5 19-7 33-7h27v80h-27c-14 0-24-2-33-7 7-17 7-49 0-66Z" fill="#191a17" />
          <path className="pen-grip-facet" d="M153 112h25v76h-25c6-17 6-59 0-76Z" fill="url(#pen-top-plane)" />
          <path className="pen-nib-feed" d="m146 138-93 12 93 12c12-5 12-19 0-24Z" fill="#11120f" stroke="#6c4c26" strokeWidth="1.5" />
          <path className="pen-nib" d="m151 123-119 27 119 27 30-14v-26Z" fill="url(#pen-nib)" stroke="#6c4b22" strokeWidth="1.25" />
          <path d="m151 123-119 27 119-5 30-8v-14Z" fill="#f7d99c" opacity=".24" />
          <path d="M151 150 43 150" fill="none" stroke="#3a2714" strokeWidth="2" />
          <circle cx="129" cy="150" r="5" fill="#53391d" stroke="#e4b96f" strokeWidth="1.2" />
          <circle cx="129" cy="149" r="1.2" fill="#f9dda2" />
          <path d="M45 150 31 150" fill="none" stroke="#1f1710" strokeWidth="2.5" strokeLinecap="round" />
          <path className="pen-body-shell" d="M174 106c10-4 21-6 35-6h372c16 0 26 10 26 24v52c0 14-10 24-26 24H209c-14 0-25-2-35-6 7-18 7-70 0-88Z" fill="url(#pen-body)" />
          <path d="M184 108c13-5 26-7 41-7h356c13 0 23 8 24 20H203c-9 0-15-4-19-13Z" fill="url(#pen-top-plane)" />
          <path d="M184 192c13 5 26 7 41 7h356c13 0 23-8 24-20H203c-9 0-15 4-19 13Z" fill="url(#pen-bottom-plane)" />
          <path d="M216 112h326c16 0 26 3 35 10H216c-11 0-18-2-24-6 7-3 14-4 24-4Z" fill="#b9a77f" opacity=".12" />
          <path d="M205 118c100 5 232 3 354-2" fill="none" stroke="#e8d39d" strokeWidth="2" opacity=".25" filter="url(#pen-glow)" />
          <path d="M203 177c122 7 240 5 355-1" fill="none" stroke="#000" strokeWidth="4" opacity=".45" />
          <path className="pen-facet-line" d="M202 134h376" fill="none" stroke="#dfc489" strokeWidth="1" opacity=".24" />
          <path className="pen-facet-line" d="M202 168h376" fill="none" stroke="#050605" strokeWidth="1.5" opacity=".75" />
          <text x="342" y="157" fill="#d7b373" opacity=".74" fontSize="9" fontFamily="Arial, sans-serif" fontWeight="700" letterSpacing="4">VALÉ / 01</text>
          <path d="M574 101h20c10 0 17 8 17 18v62c0 10-7 18-17 18h-20Z" fill="url(#pen-metal)" stroke="#4c351b" strokeWidth="1.5" />
          <path d="M583 105h10c7 0 11 7 11 14v62c0 7-4 14-11 14h-10Z" fill="#f2cb82" opacity=".26" />
          <path className="pen-cap" d="M610 104h31c31 0 56 19 56 46s-25 46-56 46h-31c8-26 8-66 0-92Z" fill="url(#pen-cap)" />
          <path d="M622 108c17 1 27 7 36 14 8 7 13 16 13 28s-5 21-13 28c-9 7-19 13-36 14 9-22 9-62 0-84Z" fill="#77705f" opacity=".17" />
          <path d="M637 110c21-1 42 8 53 22" fill="none" stroke="#d9c99f" strokeWidth="2" opacity=".22" />
          <path d="M641 110c28 2 49 16 51 37 2 22-18 39-51 43" fill="none" stroke="#050605" strokeWidth="2" opacity=".75" />
          <path className="pen-clip" d="M630 111c26-12 50-2 53 17 2 14-9 22-21 22h-17" fill="none" stroke="url(#pen-metal)" strokeWidth="5" strokeLinecap="round" />
          <circle cx="630" cy="112" r="6" fill="url(#pen-metal)" stroke="#58401f" strokeWidth="1.5" />
          <circle cx="630" cy="112" r="2" fill="#f5d899" />
          <path d="M677 142c5 3 8 8 8 13s-3 10-8 13" fill="none" stroke="#dcb977" strokeWidth="1.5" opacity=".55" />
        </g>
      </svg>
    </div>
  );
}

function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [toastVisible, setToastVisible] = useState(false);
  const sceneRef = useRef(null);
  const stageRef = useRef(null);
  const toastTimer = useRef(null);

  useEffect(() => {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduceMotion) return undefined;

    let removeListeners = () => {};
    const context = gsap.context(() => {
      gsap.set(['.hero-eyebrow', '.hero-title', '.hero-description', '.button-row', '.hero-meta'], { opacity: 0, y: 24 });
      gsap.set(sceneRef.current, { opacity: 0, x: 70, rotation: -11 });
      gsap.set('.spark', { opacity: 0, scale: 0 });

      const entrance = gsap.timeline({ defaults: { ease: 'power3.out' } });
      entrance.to('.hero-eyebrow', { opacity: 1, y: 0, duration: .8 })
        .to('.hero-title', { opacity: 1, y: 0, duration: 1 }, '-=.55')
        .to('.hero-description', { opacity: 1, y: 0, duration: .7 }, '-=.65')
        .to('.button-row', { opacity: 1, y: 0, duration: .65 }, '-=.5')
        .to('.hero-meta', { opacity: 1, y: 0, duration: .65 }, '-=.42')
        .to(sceneRef.current, { opacity: 1, x: 0, rotation: -19, duration: 1.45, ease: 'expo.out' }, '-=1.1')
        .to('.spark', { opacity: 1, scale: 1, stagger: .18, duration: .45 }, '-=.9');

      gsap.to(sceneRef.current, { y: -12, duration: 2.9, ease: 'sine.inOut', repeat: -1, yoyo: true, delay: 1.5 });
      gsap.to('.spark', { opacity: .3, scale: .65, duration: 1.4, ease: 'sine.inOut', repeat: -1, yoyo: true, stagger: .4 });

      const stage = stageRef.current;
      const handleMove = (event) => {
        const bounds = stage.getBoundingClientRect();
        const x = (event.clientX - bounds.left) / bounds.width - .5;
        const y = (event.clientY - bounds.top) / bounds.height - .5;
        gsap.to(sceneRef.current, { rotationY: -14 + x * 10, rotationX: y * -5, duration: .55, ease: 'power2.out', overwrite: true });
      };
      const handleLeave = () => gsap.to(sceneRef.current, { rotationY: -14, rotationX: 0, duration: .8, ease: 'power3.out' });
      stage.addEventListener('pointermove', handleMove);
      stage.addEventListener('pointerleave', handleLeave);

      gsap.utils.toArray('.statement-grid > *, .section-head, .feature, .edition-image, .edition-copy').forEach((element) => {
        gsap.from(element, { opacity: 0, y: 44, duration: .9, ease: 'power3.out', scrollTrigger: { trigger: element, start: 'top 84%', once: true } });
      });

      removeListeners = () => {
        stage.removeEventListener('pointermove', handleMove);
        stage.removeEventListener('pointerleave', handleLeave);
      };
    });

    return () => {
      removeListeners();
      context.revert();
    };
  }, []);

  const reserve = () => {
    setToastVisible(true);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToastVisible(false), 3200);
  };

  return (
    <div className="app-shell">
      <header className="site-header">
        <div className="shell nav">
          <Wordmark />
          <nav className={`nav-links${menuOpen ? ' open' : ''}`} aria-label="Main navigation">
            <a href="#atelier" onClick={() => setMenuOpen(false)}>The atelier</a>
            <a href="#pen" onClick={() => setMenuOpen(false)}>The pen</a>
            <a href="#edition" onClick={() => setMenuOpen(false)}>Personalise</a>
          </nav>
          <div className="nav-actions">
            <span className="nav-edition">Edition 01 / 250</span>
            <TextLink>Reserve yours</TextLink>
            <button className="menu-button" type="button" aria-label="Open menu" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? '×' : '☰'}</button>
          </div>
        </div>
      </header>

      <main id="top">
        <section className="hero" id="pen">
          <div className="shell hero-grid">
            <div className="hero-copy">
              <div className="eyebrow hero-eyebrow">The Obsidian No. 01</div>
              <h1 className="hero-title">Make your<br /><em>mark.</em></h1>
              <p className="hero-description">A precision writing instrument, composed like a grand touring automobile. For the kind of owner who chooses a Rolls-Royce for its restraint, not its noise.</p>
              <div className="button-row">
                <Button href="#edition">Discover the pen</Button>
                <TextLink href="#atelier">Explore the atelier</TextLink>
              </div>
              <div className="hero-meta">
                <div><strong>01</strong>Limited edition</div>
                <div><strong>∞</strong>Lifetime service</div>
                <div><strong>28g</strong>Balanced weight</div>
              </div>
            </div>
            <div className="product-stage" ref={stageRef} aria-label="3D render of the Obsidian No. 01 pen">
              <div className="spark one" /><div className="spark two" /><div className="spark three" />
              <div className="product-shadow" />
              <Pen sceneRef={sceneRef} />
            </div>
          </div>
        </section>

        <section className="statement" id="atelier">
          <div className="shell statement-grid">
            <div>
              <div className="eyebrow">A study in restraint</div>
              <h2>Nothing<br />extra.<br /><em>Everything</em><br />essential.</h2>
            </div>
            <div className="statement-copy">
              <p>In an age of noise, the most confident objects know when to be quiet. Obsidian No. 01 brings the discipline of coachbuilt design to the everyday ritual of writing — weight, balance and tactile pleasure, refined to a single line. The quiet confidence of a Rolls-Royce interior, translated for the hand.</p>
              <span className="signature">Made for the considered life.<small>Vale London / Since 2024</small></span>
            </div>
          </div>
        </section>

        <section className="craft" id="craft">
          <div className="shell">
            <div className="section-head">
              <div><div className="eyebrow">The engineering</div><h2>Built to be<br />remembered.</h2></div>
              <p className="section-note">Every detail earns its place. Every surface rewards the hand. This is precision you can feel before you see it.</p>
            </div>
            <div className="feature-grid">
              {features.map((feature) => <article className="feature" key={feature.number}>
                <div className="feature-number"><span>{feature.number}</span><span>{feature.number.slice(0, 2)}</span></div>
                <div className="feature-icon">{feature.icon}</div>
                <h3>{feature.title}</h3>
                <p>{feature.description}</p>
              </article>)}
            </div>
          </div>
        </section>

        <section className="edition" id="edition">
          <div className="shell edition-grid">
            <div className="edition-image">
              <div className="edition-label">OBSIDIAN / 01</div>
              <div className="mini-pen" aria-hidden="true" />
            </div>
            <div className="edition-copy">
              <div className="eyebrow">The first edition</div>
              <h2>Yours,<br />by design.</h2>
              <p>Engrave a name, a date or the words worth carrying. Your Obsidian No. 01 arrives in a hand-wrapped presentation case, ready to become part of your story.</p>
              <div className="price">£285 <small>including personalisation</small></div>
              <Button onClick={reserve}>Reserve your Obsidian</Button>
            </div>
          </div>
        </section>
      </main>

      <footer>
        <div className="shell">
          <div className="footer-top">
            <p>For those who leave an impression.</p>
            <div className="footer-links"><a href="#atelier">Journal</a><a href="#craft">Care guide</a><a href="#edition">Contact</a><a href="#top">Instagram</a></div>
          </div>
          <hr className="rule" />
          <div className="footer-bottom"><span>© 2024 Valé London</span><span>Designed with intent / Made in England</span></div>
        </div>
      </footer>
      <div className={`toast${toastVisible ? ' visible' : ''}`} role="status">Your private viewing has been reserved.</div>
    </div>
  );
}

export default App;

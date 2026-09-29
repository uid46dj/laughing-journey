import { useEffect, useRef, useState } from 'react';
import { ValeMark } from './ValeLogo.jsx';
import Modal from './Modal.jsx';
import { Arrow } from './UI.jsx';

export function Wordmark() {
  return <a className="wordmark" href="#top" aria-label="VALÉ — home"><ValeMark /><span>VALÉ</span></a>;
}

const links = [
  { href: '#atelier', label: 'The atelier', section: 'atelier' },
  { href: '#pen', label: 'The pen', section: 'pen' },
  { href: '#personalise', label: 'Personalise', section: 'personalise' },
];

export default function Header() {
  const [scrolled, setScrolled] = useState(false);
  const [active, setActive] = useState('pen');
  const [menuOpen, setMenuOpen] = useState(false);
  const frame = useRef(0);

  useEffect(() => {
    const sections = [...document.querySelectorAll('main section[id]')];
    const update = () => {
      setScrolled(window.scrollY > 24);
      const current = [...sections].reverse().find((section) => section.getBoundingClientRect().top <= window.innerHeight * .4);
      const id = current?.id || 'pen';
      setActive(id === 'atelier' || id === 'personalise' ? id : 'pen');
      frame.current = 0;
    };
    const onScroll = () => { if (!frame.current) frame.current = requestAnimationFrame(update); };
    const media = window.matchMedia('(min-width: 761px)');
    const onResize = () => { if (media.matches) setMenuOpen(false); onScroll(); };
    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onResize, { passive: true });
    return () => { window.removeEventListener('scroll', onScroll); window.removeEventListener('resize', onResize); cancelAnimationFrame(frame.current); };
  }, []);

  const closeAndNavigate = (href) => {
    setMenuOpen(false);
    // Let the dialog restore its trigger before placing focus in the destination.
    requestAnimationFrame(() => requestAnimationFrame(() => document.querySelector(href)?.focus({ preventScroll: true })));
  };

  return <>
    <a className="skip-link" href="#main">Skip to content</a>
    <header className={`site-header${scrolled ? ' is-scrolled' : ''}`}>
      <div className="shell nav">
        <Wordmark />
        <nav className="desktop-nav" aria-label="Main navigation">
          {links.map((link) => <a key={link.href} href={link.href} aria-current={active === link.section ? 'location' : undefined}>{link.label}</a>)}
        </nav>
        <div className="nav-actions">
          <span className="nav-edition">Edition 01 / 250</span>
          <a className="nav-reserve" href="#reserve"><span className="desktop-reserve-label">Reserve yours</span><span className="mobile-reserve-label">Reserve</span><Arrow /></a>
          <button className={`menu-toggle${menuOpen ? ' is-open' : ''}`} type="button" onClick={() => setMenuOpen(true)} aria-haspopup="dialog" aria-expanded={menuOpen} aria-controls="mobile-navigation" aria-label="Open menu"><span /><span /></button>
        </div>
      </div>
    </header>
    <Modal open={menuOpen} onClose={() => setMenuOpen(false)} titleId="mobile-menu-title" className="navigation-dialog">
      <div id="mobile-navigation">
        <p className="eyebrow" id="mobile-menu-title">VALÉ / London</p>
        <nav className="mobile-nav" aria-label="Mobile navigation">
          {links.map((link, index) => <a key={link.href} href={link.href} onClick={() => closeAndNavigate(link.href)} aria-current={active === link.section ? 'location' : undefined}><span className="mobile-nav-number">0{index + 1}</span><span>{link.label}</span><Arrow /></a>)}
          <a href="#reserve" onClick={() => closeAndNavigate('#reserve')}><span className="mobile-nav-number">04</span><span>Reserve yours</span><Arrow /></a>
        </nav>
        <div className="menu-footer"><span className="eyebrow">The Obsidian No. 01</span><p>For the considered life.</p><span className="caption">Edition 01 / 250</span></div>
      </div>
    </Modal>
  </>;
}

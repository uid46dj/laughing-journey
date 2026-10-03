import { useEffect } from 'react';

/** Progressive enhancement: content stays visible without JS or IntersectionObserver. */
export default function useReveal(root) {
  useEffect(() => {
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let observer;
    const elements = [...(root.current?.querySelectorAll('[data-reveal]') || [])];
    const clear = () => {
      observer?.disconnect();
      elements.forEach((element) => element.classList.remove('reveal-pending'));
    };
    const setup = () => {
      clear();
      if (motion.matches || !('IntersectionObserver' in window)) return;
      observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.remove('reveal-pending');
            observer.unobserve(entry.target);
          }
        });
      }, { rootMargin: '0px 0px -24px 0px', threshold: .08 });
      elements.forEach((element) => {
        if (element.getBoundingClientRect().top > window.innerHeight) {
          element.classList.add('reveal-pending');
          observer.observe(element);
        }
      });
    };
    // In-page links / keyboard focus must never land on unrevealed content.
    const onFocus = (event) => event.target.closest('[data-reveal]')?.classList.remove('reveal-pending');
    setup();
    motion.addEventListener('change', setup);
    document.addEventListener('focusin', onFocus);
    return () => { clear(); motion.removeEventListener('change', setup); document.removeEventListener('focusin', onFocus); };
  }, [root]);
}

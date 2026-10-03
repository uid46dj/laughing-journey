import { useId } from 'react';

/** The original product illustration, refined for full-object and macro studies.
 * No external textures or images: the same lightweight artwork powers every view.
 */
export default function Pen({ engraving = 'VALÉ / 01', view = 'full', className = '', decorative = false }) {
  const prefix = `pen-${useId().replace(/:/g, '')}`;
  const id = (name) => `${prefix}-${name}`;
  const paint = (name) => `url(#${id(name)})`;
  const views = { full: '0 0 1000 240', engraving: '340 83 330 80', finish: '675 51 310 155', nib: '35 52 315 160' };
  return (
    <svg className={`pen-render ${className}`} viewBox={views[view] || views.full} fill="none" role={decorative ? undefined : 'img'} aria-hidden={decorative || undefined} aria-labelledby={decorative ? undefined : `${id('title')} ${id('desc')}`} focusable="false">
      <title id={id('title')}>VALÉ Obsidian No. 01{view === 'engraving' ? ' — engraving preview' : ''}</title>
      <desc id={id('desc')}>An illustrated study of the black writing instrument, with a sculpted nib and champagne-toned accents.{view === 'engraving' ? ` Engraving: ${engraving || 'YOUR MARK'}.` : ''}</desc>
      <defs>
        <linearGradient id={id('barrel')} x1="0" y1="82" x2="0" y2="160" gradientUnits="userSpaceOnUse">
          <stop stopColor="#080909"/><stop offset=".12" stopColor="#242623"/><stop offset=".24" stopColor="#77786b"/><stop offset=".29" stopColor="#3e4038"/><stop offset=".38" stopColor="#191b18"/><stop offset=".6" stopColor="#111310"/><stop offset=".82" stopColor="#050605"/><stop offset=".94" stopColor="#262722"/><stop offset="1" stopColor="#080907"/>
        </linearGradient>
        <linearGradient id={id('cap')} x1="0" y1="75" x2="0" y2="166" gradientUnits="userSpaceOnUse">
          <stop stopColor="#070807"/><stop offset=".15" stopColor="#363830"/><stop offset=".23" stopColor="#8b8b7b"/><stop offset=".28" stopColor="#484b40"/><stop offset=".4" stopColor="#1d201b"/><stop offset=".75" stopColor="#080a08"/><stop offset=".9" stopColor="#1d201a"/><stop offset="1" stopColor="#080907"/>
        </linearGradient>
        <linearGradient id={id('metal')} x1="0" y1="76" x2="0" y2="164" gradientUnits="userSpaceOnUse">
          <stop stopColor="#4e432d"/><stop offset=".12" stopColor="#a49168"/><stop offset=".24" stopColor="#f4e5bc"/><stop offset=".34" stopColor="#c5ad7c"/><stop offset=".48" stopColor="#89734c"/><stop offset=".68" stopColor="#b7a077"/><stop offset=".84" stopColor="#6a5635"/><stop offset=".94" stopColor="#c8b387"/><stop offset="1" stopColor="#51442c"/>
        </linearGradient>
        <linearGradient id={id('nib')} x1="151" y1="85" x2="161" y2="150" gradientUnits="userSpaceOnUse">
          <stop stopColor="#f0dfb2"/><stop offset=".24" stopColor="#b49a68"/><stop offset=".48" stopColor="#ead5a4"/><stop offset=".52" stopColor="#8f784f"/><stop offset=".78" stopColor="#c4ac7a"/><stop offset="1" stopColor="#5d492c"/>
        </linearGradient>
        <linearGradient id={id('axial')} x1="310" y1="120" x2="704" y2="120" gradientUnits="userSpaceOnUse">
          <stop stopColor="#000" stopOpacity=".12"/><stop offset=".5" stopColor="#000" stopOpacity="0"/><stop offset="1" stopColor="#000" stopOpacity=".48"/>
        </linearGradient>
        <filter id={id('shadow')} x="-10%" y="-60%" width="120%" height="240%" colorInterpolationFilters="sRGB">
          <feDropShadow dx="0" dy="10" stdDeviation="7" floodColor="#000" floodOpacity=".48"/>
        </filter>
      </defs>
      <g filter={paint('shadow')}>
        {/* Split nib and recessed feed retain the silhouette of the original artwork. */}
        <path d="m53 123 135-24 57 5v33l-57 4Z" fill="#090a08"/>
        <path d="M48 120c39-8 89-28 142-33l46 17v32l-46 17c-53-5-103-25-142-33Z" fill={paint('nib')} stroke="#9e885e" strokeWidth=".65"/>
        <path d="M49 120c47-5 111-22 156-20l25 7" stroke="#f4e8c7" strokeOpacity=".45"/>
        <path d="m52 120 155 1" stroke="#544128" strokeWidth="1.3"/>
        <circle cx="183" cy="121" r="3.2" fill="#33291d" stroke="#d4bb8a" strokeWidth=".8"/>
        <path d="m200 103 16 17-16 17M160 103l-20 7m20 28-20-7" stroke="#6d5633" strokeWidth=".75"/>
        <path d="m170 108-12 12 12 13m-8-13h-34" stroke="#ead6a8" strokeOpacity=".5" strokeWidth=".7"/>
        <path d="M46 120h10" stroke="#d5cdb9" strokeWidth="2.5" strokeLinecap="round"/>
        {/* Tapered grip, machined seams, and fine reflective planes. */}
        <path d="M231 99c31 3 59-3 92-7l19 2v52l-19 2c-33-4-61-10-92-7 4-13 4-29 0-42Z" fill={paint('barrel')} stroke="#626253" strokeOpacity=".3"/>
        <path d="m243 107 80-7m-80 39 80 5" stroke="#b4ab8a" strokeOpacity=".19" strokeWidth=".7"/>
        <path d="M322 91h11v58h-11Z" fill={paint('metal')}/>
        <path d="M325 93v54m5-54v54" stroke="#403924" strokeWidth=".6"/>
        <path d="M334 88c73-4 246-2 364 1l22 4v54l-22 5c-118 3-291 5-364 0-6-20-6-44 0-64Z" fill={paint('barrel')} stroke="#737364" strokeOpacity=".2"/>
        <path d="M334 88c73-4 246-2 364 1l22 4v54l-22 5c-118 3-291 5-364 0-6-20-6-44 0-64Z" fill={paint('axial')}/>
        <path d="M347 97c106-3 226-2 340 0" stroke="#eddfb6" strokeOpacity=".25" strokeWidth=".8"/>
        <path d="M346 105h338m-338 41h338" stroke="#9b9b83" strokeOpacity=".14" strokeWidth=".6"/>
        <text x="510" y="125" textAnchor="middle" fill="#c5b38b" opacity=".86" fontSize="8.5" fontFamily="Arial, sans-serif" letterSpacing={engraving.length > 12 ? '1.4' : '2.6'}>{engraving || 'YOUR MARK'}</text>
        {/* Warm metal collar and posted cap. */}
        <path d="M698 80h20v80h-20c3-24 3-56 0-80Z" fill={paint('metal')}/>
        <path d="M702 81v78m11-78v78" stroke="#e7d5ad" strokeWidth=".65" opacity=".5"/>
        <path d="M717 80c47-1 139-1 189 8 25 4 41 16 41 32s-16 28-41 32c-50 9-142 9-189 8 4-25 4-55 0-80Z" fill={paint('cap')} stroke="#656858" strokeOpacity=".32"/>
        <path d="M727 89c59-2 124 0 173 7 22 3 32 9 36 16" stroke="#e1d4b1" strokeOpacity=".3" strokeWidth=".8"/>
        <path d="M726 151c68 2 135-1 177-8" stroke="#646957" strokeOpacity=".32"/>
        <path d="M922 94c15 6 24 15 24 26s-9 20-24 26" stroke={paint('metal')} strokeWidth="5"/>
        <path d="M889 88c-28-6-49-4-71-3l-76 9c-6 1-9 4-8 7 1 4 6 5 11 4l88-10c23-2 38-1 54 2Z" fill={paint('metal')} stroke="#9c8962" strokeWidth=".6"/>
        <path d="m744 97 91-9c19-1 37 0 51 3" stroke="#fff0ce" strokeOpacity=".65" strokeWidth="1"/>
        <path d="m869 111 6 10 6-10" stroke="#c5b68f" strokeWidth="1" opacity=".7"/>
      </g>
    </svg>
  );
}

export function Arrow({ direction = 'diagonal', className = '' }) {
  return <svg className={`arrow-icon ${className}`} width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"><path d={direction === 'down' ? 'M12 4v16m-6-6 6 6 6-6' : direction === 'right' ? 'M4 12h16m-6-6 6 6-6 6' : 'M5 19 19 5M5 5h14v14'} stroke="currentColor" strokeWidth="1.2" /></svg>;
}

export function Button({ href, children, className = '', ...props }) {
  const content = <><span>{children}</span><Arrow /></>;
  return href ? <a className={`button ${className}`} href={href} {...props}>{content}</a> : <button className={`button ${className}`} type="button" {...props}>{content}</button>;
}

export function TextLink({ href, children, className = '', ...props }) {
  return <a className={`text-link ${className}`} href={href} {...props}><span>{children}</span><Arrow /></a>;
}

export function SectionLabel({ number, children, className = '' }) {
  return <div className={`section-label ${className}`}><span className="eyebrow">{children}</span><span className="section-number" aria-hidden="true">{number} / VALÉ</span></div>;
}

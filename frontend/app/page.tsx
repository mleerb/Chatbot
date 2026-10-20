import Link from 'next/link';
import Icon from '../components/icon';
import Brand from '../components/brand';
import './landing.css';

export default function Page() {
  return <div className="landing" data-theme="light">
    <a className="landing-skip" href="#main">Skip to content</a>
    <header className="landing-nav landing-container">
      <Link href="/" className="landing-brand" aria-label="AGENTslop home"><span className="brand-mark" aria-hidden="true">a</span><Brand /></Link>
      <Link href="/chat" className="landing-nav-link">Open workspace <span aria-hidden="true">↗</span></Link>
    </header>
    <main id="main" className="landing-container">
      <section className="landing-hero" aria-labelledby="hero-title">
        <div>
          <p className="landing-eyebrow">Your AI agent, in one conversation</p>
          <div className="landing-signature"><Brand /></div>
          <h1 id="hero-title">Your ideas.<br /><span>Put to work.</span></h1>
          <p className="landing-description">Ask questions, explore ideas, write, and plan your next steps. Add files when you need extra context—not to get started.</p>
          <Link href="/chat" className="landing-button">Open workspace <span aria-hidden="true">↗</span></Link>
          <p className="landing-note">A local demo. No account sign-up.</p>
        </div>
        <figure className="landing-preview" aria-label="Illustrative conversation preview, not a live chat">
          <figcaption><Icon name="chat" />A quick look<span>Example</span></figcaption>
          <div className="preview-content">
            <p className="preview-question">Help me plan a launch for my new project.</p>
            <div className="preview-answer"><span className="preview-agent" aria-hidden="true">a</span><div><strong>Let’s turn it into a plan.</strong><ul><li>Define your audience and main goal.</li><li>Draft a clear launch message.</li><li>Build a checklist for the next steps.</li></ul></div></div>
            <p className="preview-followup">Tell me about your project, and we’ll work through it together.</p>
          </div>
        </figure>
      </section>
      <section id="how-it-works" className="landing-process" aria-labelledby="process-title">
        <h2 id="process-title">Three simple steps.</h2>
        <ol className="landing-steps">
          <li><span>01</span><div><h3>Start with a goal</h3><p>Ask a question or describe what you want to do. No upload needed.</p></div></li>
          <li><span>02</span><div><h3>Work with your agent</h3><p>Explore a topic, draft content, make a plan, or work with files.</p></div></li>
          <li><span>03</span><div><h3>Build on the answer</h3><p>Ask follow-ups, refine the result, and return to saved conversations.</p></div></li>
        </ol>
      </section>
    </main>
    <footer className="landing-footer landing-container"><span>AGENTslop · Local demo</span><p>Chat history is saved. Files stay in your session.</p></footer>
  </div>;
}

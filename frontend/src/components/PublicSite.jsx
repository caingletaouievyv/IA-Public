// IA/frontend/src/components/PublicSite.jsx
// Public landing and informational pages; no API or authentication required.

const pages = {
  "/privacy": {
    eyebrow: "Privacy",
    title: "Your notes stay yours.",
    intro: "IA is built around personal notes and private context. The service uses your account to scope notes, settings, and AI requests to you.",
    sections: [
      ["Data we store", "Account details, notes, settings, and credit ledger entries are stored to provide the service."],
      ["AI context", "When you ask a question, IA can use the notes and context you choose or that match your request."],
      ["Your control", "You can manage your notes and account through the app. Do not add sensitive information unless you are comfortable storing it in this deployment."],
    ],
  },
  "/terms": {
    eyebrow: "Terms",
    title: "Use IA thoughtfully.",
    intro: "IA is a personal productivity tool for organizing notes and asking questions with context.",
    sections: [
      ["Acceptable use", "Use the service lawfully and do not attempt to access another person's account, notes, or data."],
      ["AI output", "AI responses can be incomplete or inaccurate. Review important information before relying on it."],
      ["Availability", "This public deployment is provided as-is and may change, be interrupted, or be unavailable while the service evolves."],
    ],
  },
  "/contact": {
    eyebrow: "Contact",
    title: "Have a question about IA?",
    intro: "This early public site does not include a contact form yet. Support and privacy requests will be handled through the contact channel provided with the deployment.",
    sections: [
      ["Product feedback", "Share what would make asking with your notes more useful in your workflow."],
      ["Privacy requests", "Include enough detail to identify your account, but never send your password or authentication token."],
      ["Before launch", "Replace this placeholder guidance with a monitored support address before inviting public users."],
    ],
  },
};

function PublicHeader() {
  return (
    <header className="public-header">
      <a className="public-brand" href="/" aria-label="IA home">IA</a>
      <nav className="public-nav" aria-label="Public navigation">
        <a href="/privacy">Privacy</a>
        <a href="/terms">Terms</a>
        <a href="/contact">Contact</a>
        <a className="public-nav__app" href="/app">Enter IA</a>
      </nav>
    </header>
  );
}

function PublicFooter() {
  return (
    <footer className="public-footer">
      <span>IA · notes and memory with context</span>
      <nav aria-label="Footer navigation">
        <a href="/privacy">Privacy</a>
        <a href="/terms">Terms</a>
        <a href="/contact">Contact</a>
      </nav>
    </footer>
  );
}

function LandingPage() {
  return (
    <main className="public-landing">
      <section className="public-hero">
        <p className="public-kicker">A quieter way to think with AI</p>
        <h1>IA gives your notes a voice.</h1>
        <p className="public-hero__copy">
          An AI assistant that answers with the context you have already gathered, so your notes become useful when you need them.
        </p>
        <div className="public-hero__actions">
          <a className="public-cta" href="/app">Enter IA</a>
          <a className="public-text-link" href="#how-it-works">See how it works</a>
        </div>
      </section>

      <section id="how-it-works" className="public-section public-section--grid">
        <article>
          <span className="public-index">01</span>
          <h2>Keep the useful parts.</h2>
          <p>Write notes, save ideas, and bring your own material into one calm workspace.</p>
        </article>
        <article>
          <span className="public-index">02</span>
          <h2>Ask with context.</h2>
          <p>IA searches your notes and uses relevant context to make answers feel connected to your work.</p>
        </article>
        <article>
          <span className="public-index">03</span>
          <h2>Stay in your flow.</h2>
          <p>Open focused tools when you need them, then return to the ideas that matter.</p>
        </article>
      </section>

      <section className="public-callout">
        <p className="public-kicker">Built for your thinking</p>
        <h2>Start with the notes you already have.</h2>
        <a className="public-text-link" href="/app">Sign in or create an account <span aria-hidden="true">→</span></a>
      </section>
    </main>
  );
}

function InformationPage({ page }) {
  return (
    <main className="public-information">
      <p className="public-kicker">{page.eyebrow}</p>
      <h1>{page.title}</h1>
      <p className="public-information__intro">{page.intro}</p>
      <div className="public-information__sections">
        {page.sections.map(([title, copy]) => (
          <section key={title}>
            <h2>{title}</h2>
            <p>{copy}</p>
          </section>
        ))}
      </div>
    </main>
  );
}

export default function PublicSite({ path }) {
  return (
    <div className="public-site">
      <PublicHeader />
      {path === "/" ? <LandingPage /> : <InformationPage page={pages[path] || pages["/contact"]} />}
      <PublicFooter />
    </div>
  );
}

// IA/frontend/src/components/Manage.jsx
// Organize saved notes and conversation histories; retrieval memory is notes-backed.

import { useState } from "react";
import History from "./History";
import Notes from "./Notes";

const SECTIONS = [
  { id: "notes", label: "Notes" },
  { id: "conversations", label: "Conversations" },
  { id: "memory", label: "Memory" },
];

export default function Manage() {
  const [activeSection, setActiveSection] = useState("notes");

  return (
    <section className="section section--manage">
      <header className="manage-page-header">
        <h2 className="manage-page-title">Manage saved content</h2>
        <p className="card-desc">Organize your notes and saved conversations.</p>
      </header>

      <div className="manage-tabs" role="group" aria-label="Manage saved content">
        {SECTIONS.map((section) => (
          <button
            key={section.id}
            type="button"
            className={`button-subtle manage-tabs__button${activeSection === section.id ? " active" : ""}`}
            aria-pressed={activeSection === section.id}
            onClick={() => setActiveSection(section.id)}
          >
            {section.label}
          </button>
        ))}
      </div>

      {activeSection === "notes" && <Notes />}
      {activeSection === "conversations" && <History />}
      {activeSection === "memory" && (
        <section className="card app-panel manage-memory" aria-labelledby="manage-memory-title">
          <h3 className="manage-memory__title" id="manage-memory-title">Memory comes from your notes</h3>
          <p>
            IA currently retrieves relevant information from your saved notes when answering questions.
            There is no separate memory collection to manage. Create, edit, or remove source material
            in Notes; retrieval behavior is controlled by the Notes context mode in Ask.
          </p>
        </section>
      )}
    </section>
  );
}

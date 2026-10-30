// IA/frontend/src/components/Manage.jsx
// Organize saved notes, conversation histories, and independent user Memory.

import { useEffect, useState } from "react";
import History from "./History";
import MemoryManager from "./MemoryManager";
import Notes from "./Notes";

const SECTIONS = [
  { id: "notes", label: "Notes" },
  { id: "conversations", label: "Conversations" },
  { id: "memory", label: "Memory" },
];

export default function Manage({
  initialSection = "notes",
  focusNoteId = null,
  onFocusNoteHandled = null,
}) {
  const [activeSection, setActiveSection] = useState(initialSection);

  useEffect(() => {
    setActiveSection(initialSection);
  }, [initialSection]);

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

      {activeSection === "notes" && (
        <Notes focusNoteId={focusNoteId} onFocusNoteHandled={onFocusNoteHandled} />
      )}
      {activeSection === "conversations" && <History />}
      {activeSection === "memory" && <MemoryManager />}
    </section>
  );
}

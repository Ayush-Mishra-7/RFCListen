# RFCListen — Purpose & Goals

## What is RFCListen?

RFCListen is a web-based application designed for **Network Engineers, protocol designers, and students** who need to consume IETF RFC (Request for Comments) documents as part of their daily work. Instead of silently reading dense technical documents, users can **listen to RFC content read aloud** while following along visually — similar to an audiobook, but purpose-built for the structure of RFCs.

RFCs are the foundational documents of the Internet — they define protocols like TCP, HTTP, BGP, TLS, and thousands more. While critically important, they can be time-consuming to read. RFCListen turns "reading time" into "listening time," allowing engineers to absorb protocol knowledge during commutes, lab setups, or any situation where screen use is impractical.

---

## The Problem

1. **Volume**: There are over 9,000 published RFCs. Staying current with relevant ones is a challenge.
2. **Density**: RFCs contain verbose boilerplate (copyright, status pages, table of contents) that adds noise when read or listened to.
3. **Non-speakable content**: RFCs frequently include ASCII diagrams (protocol headers, state machines, message flows) that are visually meaningful but produce meaningless audio if read verbatim.
4. **No TTS tooling exists** specifically for the RFC format — general TTS tools do not understand RFC structure, sections, or figure boundaries.

---

## Goals

### Primary Goals
- **G1 — Discover**: Provide a searchable, browsable index of all published IETF RFCs sourced from the official IETF Datatracker API.
- **G2 — Listen**: Convert any RFC into a clean, listenable audio stream using Text-to-Speech, skipping boilerplate and announcing visual content.
- **G3 — Navigate**: Allow users to jump directly to any section of an RFC using a timestamp-based navigation panel, similar to chapter navigation in podcasts or audiobooks.
- **G4 — Inform**: When the audio player reaches an ASCII diagram, table, or figure, the app pauses and visually displays the content alongside a verbal announcement, so users never miss context.

### Secondary Goals
- **G5 — Speed Control**: Allow playback at adjustable speeds (0.5×–2×) so power users can absorb content faster.
- **G6 — Voice Selection**: Let users choose from available speech synthesis voices (language, gender, accent).
- **G7 — Persistence**: Remember the user's place in an RFC so they can resume listening across sessions.
- **G8 — Accessibility**: Ensure the interface is keyboard-navigable and screen-reader friendly.

---

## Target Users

| User Type | Use Case |
|-----------|----------|
| Network Engineers | Learn new protocols (e.g., QUIC, OSPF extensions) without screen time |
| Protocol Developers | Review references while working in the lab |
| Students / Certification Candidates | Study CCNP/CCIE-relevant RFCs on the go |
| Technical Writers | Research RFC content for documentation |

---

## Non-Goals (Out of Scope for MVP)

- Generating AI-summarized versions of RFCs.
- Offline/native app (this is a web-only app).
- User accounts, bookmarking, or playlist features (post-MVP).
- Audio file download/export (post-MVP).

---

## Design Principles

1. **Faithful to the Source**: Never alter the meaning of RFC text — only reformat for audio delivery.
2. **RFC-Aware Parsing**: The parser must understand RFC document conventions (RFC 7322) — not treat RFCs as generic text.
3. **Progressive Enhancement**: A fully functional MVP using the browser's built-in Web Speech API; Cloud TTS is an optional upgrade.
4. **Minimal Dependencies**: Prefer browser-native APIs and standard libraries to keep the project maintainable.

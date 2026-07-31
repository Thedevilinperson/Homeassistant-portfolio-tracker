"""
views/docs.py — pagina 'Handleiding'.
"""
from __future__ import annotations

import logging
from pathlib import Path

import streamlit as st

from views.common import (
    _section_radio
)

logger = logging.getLogger("app.docs")


# ── PAGINA: Handleiding ───────────────────────────────────────────────────────

DOC_FILES = [
    ("HANDLEIDING.md",     "📖 Handleiding",   "De volledige gebruikershandleiding"),
    ("CHANGELOG.md",       "🧾 Wijzigingen",   "Wat er per versie veranderd is, en waarom"),
    ("INSTALL_WINDOWS.md", "🪟 Windows",       "Installatie en gebruik op een Windows-PC"),
    ("DOCS.md",            "🏠 Add-on",        "De korte versie die Home Assistant toont"),
    ("README.md",          "ℹ️ Over deze app", "Korte kennismaking"),
]


# Waar een documentatiebestand kan staan. De Dockerfile kopieert de hele repo naar
# /app, dus de mapstructuur van de repository blijft behouden: INSTALL_WINDOWS.md zit
# in windows/, de rest in de hoofdmap. Een Windows-installatie draait vanuit dezelfde
# boom, maar het werkpad kan de map windows/ zelf zijn — vandaar ook '..'.
# Zoekpaden voor de documentatiebestanden, RELATIEF AAN DE APP-MAP — niet aan deze
# module. Sinds de pagina's in views/ staan, zou Path(__file__).parent naar views/
# wijzen en zouden alle paden een niveau verschuiven.
_APP_ROOT = Path(__file__).resolve().parent.parent
_DOC_DIRS = [".", "windows", "..", "../windows", "docs"]


@st.cache_data(ttl=300, show_spinner=False)
def _read_doc(fname: str) -> str | None:
    """Lees een documentatiebestand dat bij de code hoort.

    Alles komt van de schijf: geen netwerk, geen GitHub, dus ook leesbaar wanneer de
    add-on offline draait. En omdat het bestand méé geïnstalleerd is, hoort het per
    definitie bij de versie die je op dat moment gebruikt."""
    try:
        base = _APP_ROOT
        for d in _DOC_DIRS:
            p = (base / d / fname).resolve()
            if p.is_file():
                return p.read_text(encoding="utf-8")
        logger.info(f"_read_doc: {fname} niet gevonden onder {base}")
        return None
    except Exception as exc:
        logger.warning(f"_read_doc({fname}): {exc}")
        return None


def _doc_chapters(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Splits een markdowntekst op de kopniveaus '## ' in (voorwoord, hoofdstukken).

    Een handleiding van bijna twaalfhonderd regels in één keer renderen maakt de
    pagina traag en onleesbaar. Per hoofdstuk tonen houdt het overzichtelijk, en de
    zoekfunctie hieronder blijft over de volledige tekst werken.

    Wat vóór het eerste '## ' staat (de documenttitel en het versienummer) komt apart
    terug in plaats van weggegooid te worden — anders zou je in de app nergens meer
    zien welke versie van de handleiding je leest."""
    preamble, chapters, title, buf = [], [], None, []
    for line in text.split("\n"):
        if line.startswith("## ") and not line.startswith("###"):
            if title is None:
                preamble = buf
            else:
                chapters.append((title, "\n".join(buf)))
            title, buf = line[3:].strip(), []
        else:
            buf.append(line)
    if title is not None:
        chapters.append((title, "\n".join(buf)))
    else:
        preamble = buf
    return "\n".join(preamble).strip(), chapters


def page_docs():
    st.title("📖 Documentatie")
    st.caption("De volledige handleiding zit in de app zelf — geen internet nodig, en ze "
               "hoort altijd bij de versie die je draait.")

    labels = [lbl for _f, lbl, _d in DOC_FILES]
    pick = _section_radio("docs_file", labels)
    fname, _lbl, descr = next(x for x in DOC_FILES if x[1] == pick)
    text = _read_doc(fname)

    if text is None:
        st.warning(f"**{fname}** is niet gevonden bij de app. Het hoort meegeleverd te "
                   "worden met de add-on; ontbreekt het, dan is de installatie "
                   "onvolledig. Kies **Herbouwen** in Home Assistant (niet enkel "
                   "herstarten): door de laagcaching van Docker pikt een gewone "
                   "herstart nieuwe bestanden niet op.")
        return

    st.caption(descr)

    q = st.text_input("🔎 Zoeken in dit document", key=f"docs_q_{fname}",
                      placeholder="bv. fotomoment, TOB, sector, wisselkoers")
    if q.strip():
        needle = q.strip().lower()
        hits = [(i + 1, ln) for i, ln in enumerate(text.split("\n"))
                if needle in ln.lower() and ln.strip()]
        if not hits:
            st.info(f"Geen resultaat voor '{q.strip()}'.")
        else:
            st.success(f"**{len(hits)} regel(s)** met '{q.strip()}':")
            for ln_no, ln in hits[:60]:
                st.markdown(f"`{ln_no:>4}`  {ln.strip()}")
            if len(hits) > 60:
                st.caption(f"… en nog {len(hits) - 60} regels. Verfijn je zoekterm.")
        st.divider()

    preamble, chapters = _doc_chapters(text)
    if preamble:
        st.markdown(preamble)
    if len(chapters) <= 1:
        st.markdown(text if not preamble else
                    (chapters[0][1] if chapters else ""))
        return

    titles = [t for t, _c in chapters]
    ALL = "📚 Alles in één keer"
    sel = st.selectbox("Hoofdstuk", [ALL] + titles, key=f"docs_ch_{fname}")
    if sel == ALL:
        st.caption("Let op: het volledige document renderen kan even duren.")
        st.markdown(text)
    else:
        i = titles.index(sel)
        st.markdown(f"## {titles[i]}\n{chapters[i][1]}")
        nav1, nav2 = st.columns(2)
        if i > 0:
            nav1.caption(f"⬅️ Vorige: *{titles[i-1]}*")
        if i < len(titles) - 1:
            nav2.caption(f"➡️ Volgende: *{titles[i+1]}*")

    st.divider()
    st.download_button("⬇️ Dit document downloaden", text, file_name=fname,
                       mime="text/markdown", key=f"docs_dl_{fname}")

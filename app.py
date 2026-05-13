import html
import re
import streamlit as st

from auth import resolve_role, role_prefix, is_test_mode, loaded_roles
import db

CATEGORIES = ("OK", "OFFTOPIC", "MEDICAL_SENSITIVE", "CRISIS", "ATTACK")
JUST_MAX_CHARS = 150

CAT_COLORS: dict[str, tuple[str, str]] = {
    "OK":                ("#1f9d55", "#ffffff"),
    "OFFTOPIC":          ("#d69e2e", "#1a202c"),
    "MEDICAL_SENSITIVE": ("#805ad5", "#ffffff"),
    "CRISIS":            ("#dd6b20", "#ffffff"),
    "ATTACK":            ("#c53030", "#ffffff"),
}
CAT_FALLBACK = ("#4a5568", "#ffffff")

PHASE_LOGIN = "LOGIN"
PHASE_REVIEW = "REVIEW"
PHASE_CONFIRM_PICK = "CONFIRM_PICK"
PHASE_EDIT = "EDIT"
PHASE_CONFIRM_EDIT = "CONFIRM_EDIT"
PHASE_DONE = "DONE"

st.set_page_config(page_title="Data Labeling System", layout="centered")


def init_state() -> None:
    ss = st.session_state
    ss.setdefault("phase", PHASE_LOGIN)
    ss.setdefault("role", None)
    ss.setdefault("role_prefix", None)
    ss.setdefault("test_mode", False)
    ss.setdefault("record", None)
    ss.setdefault("pending_choice", None)
    ss.setdefault("edit_cat", CATEGORIES[0])
    ss.setdefault("edit_just", "")
    ss.setdefault("max_id", None)


def reset_edit_buffers() -> None:
    st.session_state.edit_cat = CATEGORIES[0]
    st.session_state.edit_just = ""


def load_next_record() -> None:
    ss = st.session_state
    rec = db.fetch_random_unrated(ss.role_prefix, ss.test_mode)
    ss.record = rec
    ss.pending_choice = None
    if rec is None:
        ss.phase = PHASE_DONE
    else:
        ss.phase = PHASE_REVIEW


def word_count(s: str) -> int:
    return len(re.findall(r"\S+", s or ""))


def models_agree(rec: dict) -> bool:
    return (rec.get("gpt_cat") or "") == (rec.get("gemini_cat") or "") and rec.get("gpt_cat") is not None


def render_login() -> None:
    st.title("Data Labeling System")
    test_mode = is_test_mode()
    if test_mode:
        st.info("Tryb testowy aktywny (`TEST_MODE=true` w `.env`) — zapis do `ysc_human_labels_test`.")
    with st.form("login"):
        secret = st.text_input("Klucz dostępu", type="password")
        submitted = st.form_submit_button("Zaloguj")
    if not submitted:
        return
    roles = loaded_roles()
    if len(roles) < 5:
        st.error(
            f"`.env` niekompletny. Załadowane role: {roles or '∅'}. "
            "Wymagane: UE, NGO, PSYCHOLOG, PSYCHIATRA, TEST."
        )
        return
    resolved = resolve_role(secret)
    if resolved is None:
        st.error("Nieprawidłowy klucz.")
        return
    role, _uuid = resolved
    st.session_state.role = role
    st.session_state.role_prefix = role_prefix(role)
    st.session_state.test_mode = test_mode
    st.session_state.max_id = db.get_max_id(test_mode)
    load_next_record()
    st.rerun()


def render_header() -> None:
    ss = st.session_state
    cols = st.columns([6, 1])
    with cols[0]:
        mode = " · TRYB TESTOWY" if ss.test_mode else ""
        st.markdown(f"**Reviewer:** `{ss.role}`{mode}")
    with cols[1]:
        if st.button("Wyloguj", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

    stats = db.get_stats(ss.role_prefix, ss.test_mode)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Ocenione", stats["total"])
    c2.metric("Oba zgodne", stats["both"])
    c3.metric("GPT", stats["gpt"])
    c4.metric("Gemini", stats["gemini"])
    c5.metric("Własne", stats["own"])

    pool = ss.max_id or 0
    if pool > 0:
        pct = min(stats["total"] / pool, 1.0)
        st.progress(pct, text=f"Postęp: {stats['total']}/{pool}  ·  {pct * 100:.1f}%")

    with st.expander("Instrukcja", expanded=False):
        cats_html = " ".join(_pill(c) for c in CATEGORIES)
        st.markdown(
            """
<div style="background:rgba(221,107,32,0.18);border-left:4px solid #dd6b20;
            padding:0.85rem 1rem;border-radius:6px;margin-bottom:0.75rem;
            font-size:1.02rem;line-height:1.45;">
<strong>Najważniejsze:</strong> oceniasz przede wszystkim <strong>kategorię</strong>.
Jeśli kategoria modelu jest poprawna — zaakceptuj, nawet gdy uzasadnienie nie jest
idealne. <strong>Nie poprawiamy uzasadnień modeli.</strong> Własne uzasadnienie wpisujesz
tylko opcjonalnie i tylko gdy wybierasz własną ocenę.
</div>
""",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
- Dla każdego tekstu otrzymujesz **dwie propozycje**: z modelu **GPT-5.5** i **Gemini-3.1-pro**.
- Aplikacja informuje, czy modele są **zgodne** czy **różnią się**.
- Możesz wybrać:
  - **Akceptuję obie** — gdy modele są zgodne i kategoria jest poprawna.
  - **Wybieram GPT** lub **Wybieram Gemini** — gdy modele różnią się, a kategoria jednej z wersji jest poprawna.
  - **Własna ocena** — gdy żadna kategoria nie pasuje. Wybierasz wtedy kategorię z listy.
- Uzasadnienie własne jest **opcjonalne** (maks. {JUST_MAX_CHARS} znaków). Wystarczy nawet jedno słowo, np. `depresja`, `kryzys`.
- Każda decyzja wymaga potwierdzenia. **Brak cofania.**

**Kolory kategorii:** {cats_html}
""",
            unsafe_allow_html=True,
        )
    st.divider()


def _pill(cat: str) -> str:
    bg, fg = CAT_COLORS.get(cat, CAT_FALLBACK)
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 10px;'
        f'border-radius:999px;font-size:0.85rem;font-weight:600;'
        f'margin-right:6px;display:inline-block;">{html.escape(cat)}</span>'
    )


def _category_card(cat: str | None, just: str | None) -> str:
    if not cat:
        return (
            '<div style="background:rgba(120,120,120,0.15);'
            'border:1px dashed rgba(120,120,120,0.4);'
            'padding:1rem;border-radius:8px;margin-bottom:0.5rem;'
            'min-height:90px;color:#888;">—</div>'
        )
    bg, fg = CAT_COLORS.get(cat, CAT_FALLBACK)
    just_html = html.escape(just).replace("\n", "<br>") if just else "<em>(brak uzasadnienia)</em>"
    return f"""
<div style="background:{bg};color:{fg};padding:1rem 1.1rem;border-radius:8px;
            margin-bottom:0.5rem;box-shadow:0 1px 4px rgba(0,0,0,0.15);">
  <div style="font-weight:700;font-size:1.05rem;letter-spacing:0.4px;
              margin-bottom:0.45rem;text-transform:uppercase;">{html.escape(cat)}</div>
  <div style="font-size:0.95rem;line-height:1.45;opacity:0.97;">{just_html}</div>
</div>
""".strip()


def _text_box(text: str) -> str:
    return f"""
<div style="background:rgba(74,144,226,0.12);
            border-left:4px solid #4a90e2;
            padding:1.1rem 1.25rem;border-radius:6px;
            font-size:1.1rem;line-height:1.55;margin:0.4rem 0 1rem 0;
            white-space:pre-wrap;">{html.escape(text)}</div>
""".strip()


def render_record_text() -> None:
    rec = st.session_state.record
    max_id = st.session_state.max_id or "?"
    st.markdown(f"### Tekst {rec['id']}/{max_id}")
    st.markdown(_text_box(rec["text"] or ""), unsafe_allow_html=True)


def render_consensus_banner(rec: dict) -> None:
    if models_agree(rec):
        st.success("Modele są **zgodne**.")
    else:
        st.warning("Modele **różnią się**.")


def render_models_panel(rec: dict) -> None:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**GPT-5.5**")
        st.markdown(_category_card(rec.get("gpt_cat"), rec.get("gpt_just")), unsafe_allow_html=True)
    with c2:
        st.markdown("**Gemini-3.1-pro**")
        st.markdown(_category_card(rec.get("gemini_cat"), rec.get("gemini_just")), unsafe_allow_html=True)


def render_review() -> None:
    rec = st.session_state.record
    render_record_text()
    render_consensus_banner(rec)

    agree = models_agree(rec)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**GPT-5.5**")
        st.markdown(_category_card(rec.get("gpt_cat"), rec.get("gpt_just")), unsafe_allow_html=True)
        if not agree:
            if st.button("Wybieram GPT", type="primary", use_container_width=True, key="pick_gpt"):
                st.session_state.pending_choice = "GPT"
                st.session_state.phase = PHASE_CONFIRM_PICK
                st.rerun()
    with c2:
        st.markdown("**Gemini-3.1-pro**")
        st.markdown(_category_card(rec.get("gemini_cat"), rec.get("gemini_just")), unsafe_allow_html=True)
        if not agree:
            if st.button("Wybieram Gemini", type="primary", use_container_width=True, key="pick_gemini"):
                st.session_state.pending_choice = "GEMINI"
                st.session_state.phase = PHASE_CONFIRM_PICK
                st.rerun()

    st.write("")
    if agree:
        if st.button("Akceptuję obie", type="primary", use_container_width=True, key="pick_both"):
            st.session_state.pending_choice = "BOTH"
            st.session_state.phase = PHASE_CONFIRM_PICK
            st.rerun()
    if st.button("Własna ocena", use_container_width=True, key="pick_own"):
        reset_edit_buffers()
        st.session_state.phase = PHASE_EDIT
        st.rerun()


def render_confirm_pick() -> None:
    rec = st.session_state.record
    choice = st.session_state.pending_choice
    render_record_text()
    render_consensus_banner(rec)
    render_models_panel(rec)
    st.divider()

    if choice == "BOTH":
        st.markdown("### Twój wybór: **akceptacja obu modeli**")
    elif choice == "GPT":
        st.markdown("### Twój wybór: **GPT-5.5**")
    elif choice == "GEMINI":
        st.markdown("### Twój wybór: **Gemini-3.1-pro**")

    st.warning("Potwierdzasz zapis tej decyzji?")
    c1, c2 = st.columns(2)
    if c1.button("Tak, zapisz", type="primary", use_container_width=True):
        db.save_choice(
            st.session_state.role_prefix,
            rec["id"],
            choice,
            None,
            None,
            st.session_state.test_mode,
        )
        load_next_record()
        st.rerun()
    if c2.button("Wróć", use_container_width=True):
        st.session_state.pending_choice = None
        st.session_state.phase = PHASE_REVIEW
        st.rerun()


def render_edit() -> None:
    rec = st.session_state.record
    render_record_text()
    render_consensus_banner(rec)
    render_models_panel(rec)
    st.divider()
    st.markdown("### Twoja własna ocena")

    st.session_state.edit_cat = st.radio(
        "Kategoria",
        CATEGORIES,
        index=CATEGORIES.index(st.session_state.edit_cat),
        horizontal=True,
    )
    st.markdown(_category_card(st.session_state.edit_cat, None), unsafe_allow_html=True)
    st.session_state.edit_just = st.text_area(
        f"Uzasadnienie (opcjonalne, maks. {JUST_MAX_CHARS} znaków)",
        value=st.session_state.edit_just,
        max_chars=JUST_MAX_CHARS,
        height=120,
        placeholder="Opcjonalnie — nawet jedno słowo wystarczy, np. „depresja”.",
    )

    n = len(st.session_state.edit_just.strip())
    w = word_count(st.session_state.edit_just)
    st.caption(f"{n}/{JUST_MAX_CHARS} znaków · {w} słów")

    c1, c2 = st.columns(2)
    if c1.button("Dalej", type="primary", use_container_width=True):
        st.session_state.phase = PHASE_CONFIRM_EDIT
        st.rerun()
    if c2.button("Wróć", use_container_width=True):
        st.session_state.phase = PHASE_REVIEW
        st.rerun()


def render_confirm_edit() -> None:
    rec = st.session_state.record
    render_record_text()
    render_consensus_banner(rec)
    render_models_panel(rec)
    st.divider()
    st.markdown("### Twoja własna ocena")
    just_clean = st.session_state.edit_just.strip()
    st.markdown(
        _category_card(st.session_state.edit_cat, just_clean or None),
        unsafe_allow_html=True,
    )
    st.warning("Potwierdzasz zapis własnej oceny?")
    c1, c2 = st.columns(2)
    if c1.button("Tak, zapisz", type="primary", use_container_width=True):
        db.save_choice(
            st.session_state.role_prefix,
            rec["id"],
            "OWN",
            st.session_state.edit_cat,
            just_clean or None,
            st.session_state.test_mode,
        )
        reset_edit_buffers()
        load_next_record()
        st.rerun()
    if c2.button("Wróć", use_container_width=True):
        st.session_state.phase = PHASE_EDIT
        st.rerun()


def render_done() -> None:
    st.success("Brak rekordów do oceny dla Twojej roli.")


def main() -> None:
    init_state()
    if st.session_state.phase == PHASE_LOGIN:
        render_login()
        return

    render_header()
    phase = st.session_state.phase
    if phase == PHASE_REVIEW:
        render_review()
    elif phase == PHASE_CONFIRM_PICK:
        render_confirm_pick()
    elif phase == PHASE_EDIT:
        render_edit()
    elif phase == PHASE_CONFIRM_EDIT:
        render_confirm_edit()
    elif phase == PHASE_DONE:
        render_done()


main()

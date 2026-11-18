import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
import base64
from pathlib import Path
import os

API_URL = os.getenv("API_URL", "http://localhost:8000")
DEFAULT_TIMEOUT = 15   # seconds, for quick endpoints
CHAT_TIMEOUT = 120     # seconds, LLM answers can be slow

APP_NAME = "FinSight"

st.set_page_config(page_title=APP_NAME, page_icon="📊", layout="wide")
# -------------------------
# BACKGROUND IMAGES
# -------------------------
# Resolved relative to this file, so it works no matter where streamlit is launched from.
BG_IMAGE = Path(__file__).resolve().parent.parent / "static" / "images" / "background.jpg"
BG_OVERLAY = "rgba(10, 15, 25, 0.60)"  # dark tint over the photo; raise alpha for more contrast


@st.cache_data(show_spinner=False)
def load_image_b64(image_path):
    """Read and base64-encode the background once, not on every rerun.
    Returns None if the file is missing so the app still loads."""
    try:
        return base64.b64encode(Path(image_path).read_bytes()).decode()
    except OSError:
        return None


def apply_page_styles(image_path):
    encoded = load_image_b64(str(image_path))
    if encoded:
        background = (
            f"linear-gradient({BG_OVERLAY}, {BG_OVERLAY}), "
            f'url("data:image/jpg;base64,{encoded}")'
        )
    else:
        background = f"linear-gradient({BG_OVERLAY}, {BG_OVERLAY})"

    st.markdown(f"""
    <style>
    .stApp {{
        background-image: {background};
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        background-attachment: fixed;
    }}
    /* Keep the top bar transparent so the overlay shows through */
    [data-testid="stHeader"] {{
        background: transparent;
    }}
    /* Content sits on a light, slightly translucent card for readability */
    [data-testid="stMainBlockContainer"], .main .block-container {{
        background: rgba(255, 255, 255, 0.94);
        border-radius: 12px;
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.35);
        margin-top: 3rem;
        margin-bottom: 2rem;
        padding: 2rem 2.5rem;
        max-width: 1100px;
    }}
    @media (max-width: 640px) {{
        [data-testid="stMainBlockContainer"], .main .block-container {{
            padding: 1.25rem 1rem;
            margin-top: 2.5rem;
        }}
    }}
    .app-header {{
        text-align: center;
        margin-bottom: 1rem;
    }}
    .app-header h2 {{
        margin: 0;
        padding: 0;
    }}
    .app-header p {{
        margin: 0.25rem 0 0;
        color: #555;
    }}
    </style>
    """, unsafe_allow_html=True)


apply_page_styles(BG_IMAGE)

st.markdown(f"""
<div class="app-header">
    <h2>📊 {APP_NAME}</h2>
    <p>Your document assistant for insights about FinSolve Technologies.</p>
</div>
""", unsafe_allow_html=True)

# -------------------------
# SESSION INIT
# -------------------------
if "auth" not in st.session_state:
    st.session_state.auth = None
if "role" not in st.session_state:
    st.session_state.role = None
if "page" not in st.session_state:
    st.session_state.page = "login"
if "messages" not in st.session_state:
    st.session_state.messages = []

# Everything tied to a logged-in user; wiped on logout.
SESSION_USER_KEYS = ("auth", "role", "username", "password", "roles", "messages")


def logout():
    for key in SESSION_USER_KEYS:
        st.session_state.pop(key, None)
    st.session_state.auth = None
    st.session_state.role = None
    st.session_state.messages = []
    st.session_state.page = "login"


# -------------------------
# API HELPERS
# -------------------------
def api_request(method, path, timeout=DEFAULT_TIMEOUT, show_errors=True, **kwargs):
    """Call the backend. Returns the Response, or None if the request itself failed
    (backend down, timeout, etc.). Request arguments are passed through unchanged."""
    try:
        return requests.request(method, f"{API_URL}{path}", timeout=timeout, **kwargs)
    except requests.exceptions.ConnectionError:
        msg = "Can't reach the server. Make sure the FastAPI backend is running."
    except requests.exceptions.Timeout:
        msg = "The server took too long to respond. Please try again."
    except requests.exceptions.RequestException as e:
        msg = f"Request failed: {e}"
    if show_errors:
        st.error(msg)
    return None


def error_detail(res, fallback="Something went wrong."):
    """Extract FastAPI's 'detail' message, tolerating non-JSON error bodies."""
    try:
        detail = res.json().get("detail")
    except (ValueError, AttributeError):
        detail = None
    return detail if isinstance(detail, str) and detail else fallback


# Load roles into session state if not present
def fetch_roles():
    res = api_request("GET", "/roles", auth=HTTPBasicAuth(*st.session_state.auth), show_errors=False)
    if res is None or not res.ok:
        return []
    try:
        return res.json().get("roles", [])
    except ValueError:
        return []


# -------------------------
# LOGIN PAGE
# -------------------------
if st.session_state.page == "login":
    _, center, _ = st.columns([1, 1.4, 1])
    with center:
        with st.form("login_form"):
            st.subheader("Sign in")
            username = st.text_input("Username", autocomplete="username")
            password = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Sign in", type="primary", width="stretch")

        # Messages render outside the form so they stay visible below it.
        if submitted and (not username.strip() or not password):
            st.warning("Please enter both username and password.")
            submitted = False

    if submitted:
        with center, st.spinner("Signing in…"):
            res = api_request("GET", "/login", auth=HTTPBasicAuth(username, password))
        if res is None:
            pass  # connection error already shown
        elif res.status_code == 200:
            st.session_state.auth = (username, password)
            st.session_state.username = username
            st.session_state.password = password
            st.session_state.role = res.json()["role"]
        
            # Fetch roles once login is successful
            st.session_state.roles = fetch_roles()

            st.session_state.page = "main"  # Navigate to main app
            st.rerun()
        else:
            with center:
                st.error(error_detail(res, "Login failed."))


# -------------------------
# MAIN APP AFTER LOGIN
# -------------------------
def flash(message):
    """Queue a success message that survives an st.rerun()."""
    st.session_state.flash = message


def access_summary(role):
    if role == "C-Level":
        return "all documents"
    if role == "General":
        return "General documents"
    return f"{role} + General documents"


if st.session_state.page == "main":
    username = st.session_state.username
    role = st.session_state.role
    is_admin = role == "C-Level"
    roles = st.session_state.get("roles") or []

    if "flash" in st.session_state:
        st.toast(st.session_state.pop("flash"), icon="✅")

    with st.sidebar:
        st.markdown(f"**User:** {username}  \n**Role:** {role}")
        st.divider()
        if st.button("Log out", icon="🚪", width="stretch"):
            logout()
            st.rerun()

    st.caption(
        f"Signed in as **{username}** · Role: **{role}** · Access: {access_summary(role)}"
    )

    if is_admin:
        tab1, tab2, tab3 = st.tabs(["💬 Chat", "📤 Upload", "🛠️ Admin"])
    else:
        (tab1,) = st.tabs(["💬 Chat"])

    # --- Chat Tab ---
    with tab1:
        # Messages go in a container placed above the input box, so new
        # messages appear above the input rather than below it.
        history = st.container()
        question = st.chat_input("Ask a question about your documents…")

        with history:
            if not st.session_state.messages:
                st.caption("Ask anything about the documents your role can access.")
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]):
                    if msg.get("error"):
                        st.error(msg["content"])
                    else:
                        st.markdown(msg["content"])

            if question and question.strip():
                st.session_state.messages.append({"role": "user", "content": question})
                with st.chat_message("user"):
                    st.markdown(question)

                with st.chat_message("assistant"):
                    with st.spinner("Thinking…"):
                        res = api_request(
                            "POST", "/chat",
                            timeout=CHAT_TIMEOUT,
                            show_errors=False,
                            json={"question": question, "role": st.session_state.role},
                            auth=HTTPBasicAuth(*st.session_state.auth)
                        )
                    answer, is_error = None, True
                    if res is None:
                        answer = "Can't reach the server, or it took too long to respond. Please try again."
                    elif res.status_code == 200:
                        try:
                            answer, is_error = res.json()["answer"], False
                        except (ValueError, KeyError):
                            answer = "The server returned an unexpected response."
                    else:
                        answer = error_detail(res, "Something went wrong while processing your question.")

                    if is_error:
                        st.error(answer)
                    else:
                        st.markdown(answer)
                st.session_state.messages.append(
                    {"role": "assistant", "content": answer, "error": is_error}
                )


    # --- Admin-only tabs ---
    if is_admin:
        if not roles:
            for tab, key in ((tab2, "retry_roles_upload"), (tab3, "retry_roles_admin")):
                with tab:
                    st.warning("Couldn't load the list of roles from the server.")
                    if st.button("Retry", key=key):
                        st.session_state.roles = fetch_roles()
                        st.rerun()

        # --- Upload Tab ---
        with tab2:
            st.subheader("Upload a document")
            with st.form("upload_form", clear_on_submit=True):
                selected_role = st.selectbox(
                    "Who can access this document?", roles,
                    help="Users with this role will be able to query the document.",
                )
                doc_file = st.file_uploader("Document (.md or .csv)", type=["csv", "md"])
                upload_clicked = st.form_submit_button("Upload", type="primary")

            if upload_clicked:
                if doc_file is None:
                    st.warning("Choose a file to upload.")
                elif not selected_role:
                    st.warning("Choose an access role.")
                else:
                    with st.spinner(f"Uploading {doc_file.name}…"):
                        res = api_request(
                            "POST", "/upload-docs",
                            files={"file": doc_file},
                            data={"role": selected_role},
                            auth=HTTPBasicAuth(*st.session_state.auth)
                        )
                    if res is None:
                        pass  # connection error already shown
                    elif res.ok:
                        st.success(res.json().get("message", "Document uploaded."))
                    else:
                        st.error(error_detail(res))

        # --- Admin Tab ---
        with tab3:
            st.subheader("Add a user")
            with st.form("create_user_form", clear_on_submit=True):
                new_user = st.text_input("Username")
                new_pass = st.text_input("Password", type="password")
                new_role = st.selectbox("Role", roles)
                create_user_clicked = st.form_submit_button("Create user", type="primary")

            if create_user_clicked:
                new_user = new_user.strip()
                if not new_user or not new_pass:
                    st.warning("Enter both a username and a password.")
                elif not new_role:
                    st.warning("Choose a role for the new user.")
                else:
                    res = api_request(
                        "POST", "/create-user",
                        data={"username": new_user, "password": new_pass, "role": new_role},
                        auth=HTTPBasicAuth(*st.session_state.auth)
                    )
                    if res is None:
                        pass  # connection error already shown
                    elif res.ok:
                        st.success(res.json().get("message", f"User '{new_user}' created."))
                    else:
                        st.error(error_detail(res))

            st.divider()

            st.subheader("Create a role")
            with st.form("create_role_form", clear_on_submit=True):
                new_role_input = st.text_input("Role name")
                create_role_clicked = st.form_submit_button("Add role", type="primary")

            if create_role_clicked:
                new_role_input = new_role_input.strip()
                if not new_role_input:
                    st.warning("Enter a role name.")
                elif new_role_input.lower() in (r.lower() for r in roles):
                    st.warning(f"The role '{new_role_input}' already exists.")
                else:
                    res = api_request(
                        "POST", "/create-role",
                        data={"role_name": new_role_input},
                        auth=HTTPBasicAuth(*st.session_state.auth)
                    )
                    if res is None:
                        pass  # connection error already shown
                    elif res.ok:
                        # Message is shown after the rerun so it isn't lost.
                        flash(res.json().get("message", f"Role '{new_role_input}' created."))
                        st.session_state.roles = fetch_roles()  # Refresh role dropdowns
                        st.rerun()
                    else:
                        st.error(error_detail(res))

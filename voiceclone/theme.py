"""A clean light theme with Discord-blurple accents (pure ttk, no extra deps)."""
from tkinter import ttk

PALETTE = {
    "bg": "#f4f5f7",
    "field": "#ffffff",
    "text": "#2e3338",
    "muted": "#6b7280",
    "accent": "#5865f2",
    "accent_active": "#4752c4",
    "danger": "#ed4245",
    "header": "#5865f2",
    "status": "#e9eaee",
}

BASE = ("Segoe UI", 10)
SEMI = ("Segoe UI Semibold", 10)


def apply_theme(root):
    p = PALETTE
    root.configure(bg=p["bg"])
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except Exception:
        pass

    st.configure(".", background=p["bg"], foreground=p["text"], font=BASE)
    st.configure("TFrame", background=p["bg"])
    st.configure("TLabel", background=p["bg"], foreground=p["text"], font=BASE)
    st.configure("Title.TLabel", font=("Segoe UI Semibold", 15))
    st.configure("Muted.TLabel", foreground=p["muted"], font=("Segoe UI", 9))
    st.configure("Status.TLabel", background=p["status"], foreground=p["text"],
                 font=("Segoe UI", 9), padding=6)

    st.configure("TButton", background=p["field"], foreground=p["text"],
                 padding=(12, 6), borderwidth=1)
    st.map("TButton", background=[("active", "#eef0ff")],
           bordercolor=[("focus", p["accent"])])
    st.configure("Accent.TButton", background=p["accent"], foreground="#ffffff",
                 padding=(14, 7), borderwidth=0)
    st.map("Accent.TButton", background=[("active", p["accent_active"]),
                                         ("disabled", "#b9bdf0")])
    st.configure("Danger.TButton", background=p["field"], foreground=p["danger"],
                 padding=(12, 6))
    st.map("Danger.TButton", background=[("active", "#ffe9ea")])

    st.configure("TNotebook", background=p["bg"], borderwidth=0, tabmargins=(8, 6, 8, 0))
    st.configure("TNotebook.Tab", background=p["bg"], foreground=p["muted"],
                 padding=(18, 9), font=BASE, borderwidth=0)
    st.map("TNotebook.Tab", background=[("selected", p["field"])],
           foreground=[("selected", p["accent"])])

    st.configure("Treeview", background=p["field"], fieldbackground=p["field"],
                 foreground=p["text"], rowheight=27, borderwidth=1)
    st.configure("Treeview.Heading", background="#eceef1", foreground=p["muted"],
                 font=("Segoe UI Semibold", 9), padding=6, relief="flat")
    st.map("Treeview", background=[("selected", p["accent"])],
           foreground=[("selected", "#ffffff")])

    st.configure("TCheckbutton", background=p["bg"], foreground=p["text"])
    st.map("TCheckbutton", background=[("active", p["bg"])])
    st.configure("TLabelframe", background=p["bg"], borderwidth=1, relief="solid")
    st.configure("TLabelframe.Label", background=p["bg"], foreground=p["muted"],
                 font=("Segoe UI Semibold", 9))
    st.configure("TEntry", fieldbackground=p["field"], padding=4)
    st.configure("TCombobox", fieldbackground=p["field"], padding=4)
    st.configure("TSpinbox", fieldbackground=p["field"], padding=3)
    st.configure("Horizontal.TScale", background=p["bg"])
    return p

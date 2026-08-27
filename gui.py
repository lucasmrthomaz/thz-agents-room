"""
THZ Minds — Interface Tkinter
Motor Multiagente Local com 8 LLMs
"""

import asyncio
import json
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, Scrollbar
import websockets

URI = "ws://127.0.0.1:8000/ws/debate"

# Cores do tema
BG_DARK = "#1e1e2e"
BG_MID = "#282840"
BG_LIGHT = "#313150"
FG_PRIMARY = "#cdd6f4"
FG_DIM = "#6c7086"
FG_BRIGHT = "#ffffff"
ACCENT_BLUE = "#89b4fa"
ACCENT_GREEN = "#a6e3a1"
ACCENT_YELLOW = "#f9e2af"
ACCENT_RED = "#f38ba8"
ACCENT_MAGENTA = "#cba6f7"
ACCENT_CYAN = "#94e2d5"
ACCENT_ORANGE = "#fab387"

# Cores dos agentes
AGENT_COLORS = {
    "Arquiteto": "#94e2d5",
    "SRE": "#f38ba8",
    "DevOps": "#a6e3a1",
    "DBA": "#f9e2af",
    "Security": "#cba6f7",
    "PO": "#89b4fa",
    "Scrum Master": "#cdd6f4",
    "Gerente": "#fab387",
}

STATUS_COLORS = {
    "CONTINUE": "#f9e2af",
    "CONSENSUS": "#a6e3a1",
    "STOP": "#f38ba8",
    "FORCE_STOP": "#f38ba8",
}

# Animacao de loading
LOADING_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class THZMainsApp:
    """Aplicacao principal THZ Minds."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("THZ Minds — Motor Multiagente Local & TeamWork")
        self.root.geometry("1260x860")
        self.root.minsize(920, 620)
        self.root.configure(bg=BG_DARK)

        self.server_running = False
        self.connected = False
        self.ws = None
        self.loop = None
        self.thread = None
        self.running = False
        self.current_mode = None
        self.loading_frame = 0
        self.loading_active = False
        self.step_start_time = 0.0
        self.active_file_info = None
        self.current_turn = 0
        self.max_turns = 48

        self._setup_styles()
        self._build_ui()
        self._start_server()

    def _setup_styles(self):
        """Configura estilos do tkinter."""
        self.style = ttk.Style()
        self.style.theme_use("clam")

        self.style.configure("TFrame", background=BG_DARK)
        self.style.configure("TLabel", background=BG_DARK, foreground=FG_PRIMARY, font=("Segoe UI", 10))
        self.style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=8)
        self.style.configure("Accent.TButton", background=ACCENT_BLUE, foreground=BG_DARK)
        self.style.configure("Stop.TButton", background=ACCENT_RED, foreground=BG_DARK)
        self.style.configure("TEntry", font=("Segoe UI", 11))
        self.style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"), foreground=ACCENT_CYAN)
        self.style.configure("Sub.TLabel", font=("Segoe UI", 9), foreground=FG_DIM)
        self.style.configure("Status.TLabel", font=("Consolas", 9), foreground=FG_DIM)
        self.style.configure("Loading.TLabel", font=("Consolas", 11, "bold"), foreground=ACCENT_YELLOW)

        # Abas Notebook
        self.style.configure("TNotebook", background=BG_DARK, borderwidth=0)
        self.style.configure("TNotebook.Tab", background=BG_MID, foreground=FG_PRIMARY, font=("Segoe UI", 9, "bold"), padding=[10, 5])
        self.style.map("TNotebook.Tab", background=[("selected", BG_LIGHT)], foreground=[("selected", ACCENT_CYAN)])

    def _build_ui(self):
        """Constrói a interface."""
        # Header
        header = ttk.Frame(self.root)
        header.pack(fill=tk.X, padx=15, pady=(15, 5))

        ttk.Label(header, text="🧠 THZ Minds", style="Header.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, text="Motor Multiagente Local", style="Sub.TLabel").pack(side=tk.LEFT, padx=(10, 0), pady=(5, 0))

        # Status do servidor
        self.server_status = tk.Label(
            header, text="● Iniciando servidor...", fg=ACCENT_YELLOW, bg=BG_DARK, font=("Segoe UI", 9)
        )
        self.server_status.pack(side=tk.RIGHT)

        # Separador
        ttk.Separator(self.root, orient="horizontal").pack(fill=tk.X, padx=15, pady=5)

        # Controles - Linha 1: Modo, Parâmetros e Ações Principais
        controls_row1 = ttk.Frame(self.root)
        controls_row1.pack(fill=tk.X, padx=15, pady=(5, 4))

        # Modo
        mode_frame = ttk.Frame(controls_row1)
        mode_frame.pack(side=tk.LEFT, padx=(0, 15))

        ttk.Label(mode_frame, text="Modo:").pack(side=tk.LEFT, padx=(0, 4))

        self.mode_var = tk.StringVar(value="single")
        self.btn_single = tk.Radiobutton(
            mode_frame, text="💬 Debate", variable=self.mode_var, value="single",
            bg=BG_DARK, fg=ACCENT_BLUE, selectcolor=BG_MID, activebackground=BG_DARK,
            activeforeground=ACCENT_BLUE, font=("Segoe UI", 9, "bold"), command=self._on_mode_change
        )
        self.btn_single.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_eng = tk.Radiobutton(
            mode_frame, text="⚙️ Engenharia", variable=self.mode_var, value="engineering",
            bg=BG_DARK, fg=ACCENT_GREEN, selectcolor=BG_MID, activebackground=BG_DARK,
            activeforeground=ACCENT_GREEN, font=("Segoe UI", 9, "bold"), command=self._on_mode_change
        )
        self.btn_eng.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_content = tk.Radiobutton(
            mode_frame, text="✍️ Artigo", variable=self.mode_var, value="content",
            bg=BG_DARK, fg=ACCENT_MAGENTA, selectcolor=BG_MID, activebackground=BG_DARK,
            activeforeground=ACCENT_MAGENTA, font=("Segoe UI", 9, "bold"), command=self._on_mode_change
        )
        self.btn_content.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_autonomous = tk.Radiobutton(
            mode_frame, text="🌙 Noturno", variable=self.mode_var, value="autonomous",
            bg=BG_DARK, fg=ACCENT_YELLOW, selectcolor=BG_MID, activebackground=BG_DARK,
            activeforeground=ACCENT_YELLOW, font=("Segoe UI", 9, "bold"), command=self._on_mode_change
        )
        self.btn_autonomous.pack(side=tk.LEFT)

        # Parâmetros (Modelo, Turnos, Horas)
        params_frame = ttk.Frame(controls_row1)
        params_frame.pack(side=tk.LEFT, padx=(0, 15))

        ttk.Label(params_frame, text="Modelo:").pack(side=tk.LEFT, padx=(0, 2))
        self.model_var = tk.StringVar(value="auto")
        self.model_entry = tk.Entry(
            params_frame, textvariable=self.model_var, width=14,
            font=("Consolas", 9), bg=BG_MID, fg=FG_PRIMARY, relief=tk.FLAT,
            highlightthickness=1, highlightbackground=FG_DIM
        )
        self.model_entry.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(params_frame, text="Turnos:").pack(side=tk.LEFT, padx=(0, 2))
        self.turns_var = tk.StringVar(value="48")
        self.turns_entry = tk.Entry(
            params_frame, textvariable=self.turns_var, width=4,
            font=("Consolas", 9), bg=BG_MID, fg=FG_PRIMARY, relief=tk.FLAT,
            highlightthickness=1, highlightbackground=FG_DIM
        )
        self.turns_entry.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(params_frame, text="Duração (h):").pack(side=tk.LEFT, padx=(0, 2))
        self.hours_var = tk.StringVar(value="8")
        self.hours_entry = tk.Entry(
            params_frame, textvariable=self.hours_var, width=4,
            font=("Consolas", 9), bg=BG_MID, fg=FG_PRIMARY, relief=tk.FLAT,
            highlightthickness=1, highlightbackground=FG_DIM
        )
        self.hours_entry.pack(side=tk.LEFT)
        self.hours_entry.config(state=tk.DISABLED)

        # Botões de Ação
        btn_frame = ttk.Frame(controls_row1)
        btn_frame.pack(side=tk.RIGHT)

        self.start_btn = tk.Button(
            btn_frame, text="▶ Iniciar", font=("Segoe UI", 10, "bold"),
            bg=ACCENT_GREEN, fg=BG_DARK, relief=tk.FLAT, padx=14, pady=4,
            command=self._start_debate, state=tk.NORMAL, cursor="hand2"
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.stop_btn = tk.Button(
            btn_frame, text="■ Parar", font=("Segoe UI", 10, "bold"),
            bg=ACCENT_RED, fg=BG_DARK, relief=tk.FLAT, padx=14, pady=4,
            command=self._stop_debate, state=tk.DISABLED, cursor="hand2"
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.output_btn = tk.Button(
            btn_frame, text="📂 Pasta output/", font=("Segoe UI", 9, "bold"),
            bg=BG_LIGHT, fg=FG_PRIMARY, relief=tk.FLAT, padx=10, pady=4,
            command=self._open_output_folder, cursor="hand2"
        )
        self.output_btn.pack(side=tk.LEFT)

        # Controles - Linha 2: Campo de Tópico / Desafio em Largura Total
        controls_row2 = ttk.Frame(self.root)
        controls_row2.pack(fill=tk.X, padx=15, pady=(0, 5))

        ttk.Label(controls_row2, text="Tópico / Desafio:", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=(0, 6))

        self.topic_entry = tk.Entry(
            controls_row2, font=("Segoe UI", 11), bg=BG_MID, fg=FG_PRIMARY,
            insertbackground=FG_PRIMARY, relief=tk.FLAT, highlightthickness=1,
            highlightbackground=FG_DIM, highlightcolor=ACCENT_BLUE
        )
        self.topic_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.topic_entry.bind("<Return>", lambda e: self._start_debate())

        self.scenario_btn = tk.Button(
            controls_row2, text="🎲 Gerar Cenário Real", font=("Segoe UI", 9, "bold"),
            bg=BG_LIGHT, fg=ACCENT_CYAN, relief=tk.FLAT, padx=12, pady=4,
            command=self._fill_random_scenario, cursor="hand2"
        )
        self.scenario_btn.pack(side=tk.RIGHT)

        # Separador
        ttk.Separator(self.root, orient="horizontal").pack(fill=tk.X, padx=15, pady=4)

        # Loading indicator
        self.loading_frame_label = tk.Label(
            self.root, text="", fg=ACCENT_CYAN, bg=BG_DARK,
            font=("Consolas", 12), anchor=tk.W
        )
        self.loading_frame_label.pack(fill=tk.X, padx=15, pady=(0, 2))

        # Area principal com PanedWindow (sidebar + debate)
        main_pane = tk.PanedWindow(
            self.root, orient=tk.HORIZONTAL, bg=BG_DARK,
            sashwidth=4, sashrelief=tk.FLAT, borderwidth=0
        )
        main_pane.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 5))

        # === SIDEBAR COM ABAS ===
        sidebar_frame = tk.Frame(main_pane, bg=BG_DARK, width=280)
        main_pane.add(sidebar_frame, minsize=240, width=280)

        self.sidebar_notebook = ttk.Notebook(sidebar_frame)
        self.sidebar_notebook.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # --- ABA 1: DEBATES ---
        tab_debates = tk.Frame(self.sidebar_notebook, bg=BG_DARK)
        self.sidebar_notebook.add(tab_debates, text=" 💬 Debates ")

        debates_header = tk.Frame(tab_debates, bg=BG_DARK)
        debates_header.pack(fill=tk.X, padx=5, pady=(5, 5))
        tk.Label(debates_header, text="Histórico de Debates", fg=ACCENT_CYAN, bg=BG_DARK, font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        self.refresh_btn = tk.Button(
            debates_header, text="↻ Atualizar", fg=ACCENT_CYAN, bg=BG_MID,
            font=("Segoe UI", 9, "bold"), relief=tk.FLAT, bd=0, padx=6, pady=2,
            command=self._load_debate_history, cursor="hand2"
        )
        self.refresh_btn.pack(side=tk.RIGHT)

        sidebar_list_frame = tk.Frame(tab_debates, bg=BG_MID, relief=tk.FLAT)
        sidebar_list_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=(0, 2))

        self.sidebar_canvas = tk.Canvas(sidebar_list_frame, bg=BG_MID, highlightthickness=0, bd=0)
        self.sidebar_scrollbar = tk.Scrollbar(sidebar_list_frame, orient=tk.VERTICAL, command=self.sidebar_canvas.yview)
        self.sidebar_inner = tk.Frame(self.sidebar_canvas, bg=BG_MID)
        self.sidebar_inner.bind("<Configure>", lambda e: self.sidebar_canvas.configure(scrollregion=self.sidebar_canvas.bbox("all")))
        self.sidebar_canvas.create_window((0, 0), window=self.sidebar_inner, anchor=tk.NW)
        self.sidebar_canvas.configure(yscrollcommand=self.sidebar_scrollbar.set)
        self.sidebar_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.sidebar_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.sidebar_canvas.bind("<MouseWheel>", lambda e: self.sidebar_canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        self.debate_entries = []
        self.debate_ids = []

        # --- ABA 2: PROJETOS GERADOS (OUTPUT) ---
        tab_projects = tk.Frame(self.sidebar_notebook, bg=BG_DARK)
        self.sidebar_notebook.add(tab_projects, text=" 📦 Projetos ")

        projects_header = tk.Frame(tab_projects, bg=BG_DARK)
        projects_header.pack(fill=tk.X, padx=5, pady=(5, 5))
        tk.Label(projects_header, text="Fábrica (output/)", fg=ACCENT_GREEN, bg=BG_DARK, font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        self.refresh_projects_btn = tk.Button(
            projects_header, text="↻ Atualizar", fg=ACCENT_GREEN, bg=BG_MID,
            font=("Segoe UI", 9, "bold"), relief=tk.FLAT, bd=0, padx=6, pady=2,
            command=self._load_projects_history, cursor="hand2"
        )
        self.refresh_projects_btn.pack(side=tk.RIGHT)

        projects_list_frame = tk.Frame(tab_projects, bg=BG_MID, relief=tk.FLAT)
        projects_list_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=(0, 2))

        self.projects_canvas = tk.Canvas(projects_list_frame, bg=BG_MID, highlightthickness=0, bd=0)
        self.projects_scrollbar = tk.Scrollbar(projects_list_frame, orient=tk.VERTICAL, command=self.projects_canvas.yview)
        self.projects_inner = tk.Frame(self.projects_canvas, bg=BG_MID)
        self.projects_inner.bind("<Configure>", lambda e: self.projects_canvas.configure(scrollregion=self.projects_canvas.bbox("all")))
        self.projects_canvas.create_window((0, 0), window=self.projects_inner, anchor=tk.NW)
        self.projects_canvas.configure(yscrollcommand=self.projects_scrollbar.set)
        self.projects_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.projects_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.projects_canvas.bind("<MouseWheel>", lambda e: self.projects_canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        self.project_entries = []

        # --- ABA 3: CONHECIMENTO ---
        tab_knowledge = tk.Frame(self.sidebar_notebook, bg=BG_DARK)
        self.sidebar_notebook.add(tab_knowledge, text=" 🧠 Conhecimento ")

        knowledge_header = tk.Frame(tab_knowledge, bg=BG_DARK)
        knowledge_header.pack(fill=tk.X, padx=5, pady=(5, 5))
        tk.Label(knowledge_header, text="Tópicos & Skills", fg=ACCENT_MAGENTA, bg=BG_DARK, font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        self.refresh_knowledge_btn = tk.Button(
            knowledge_header, text="↻ Atualizar", fg=ACCENT_MAGENTA, bg=BG_MID,
            font=("Segoe UI", 9, "bold"), relief=tk.FLAT, bd=0, padx=6, pady=2,
            command=self._load_knowledge_base, cursor="hand2"
        )
        self.refresh_knowledge_btn.pack(side=tk.RIGHT)

        knowledge_list_frame = tk.Frame(tab_knowledge, bg=BG_MID, relief=tk.FLAT)
        knowledge_list_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=(0, 2))

        self.knowledge_canvas = tk.Canvas(knowledge_list_frame, bg=BG_MID, highlightthickness=0, bd=0)
        self.knowledge_scrollbar = Scrollbar(knowledge_list_frame, orient=tk.VERTICAL, command=self.knowledge_canvas.yview)
        self.knowledge_inner = tk.Frame(self.knowledge_canvas, bg=BG_MID)
        self.knowledge_inner.bind("<Configure>", lambda e: self.knowledge_canvas.configure(scrollregion=self.knowledge_canvas.bbox("all")))
        self.knowledge_canvas.create_window((0, 0), window=self.knowledge_inner, anchor=tk.NW)
        self.knowledge_canvas.configure(yscrollcommand=self.knowledge_scrollbar.set)
        self.knowledge_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.knowledge_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.knowledge_canvas.bind("<MouseWheel>", lambda e: self.knowledge_canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        # === AREA DE DEBATE / VISUALIZADOR ===
        debate_frame = tk.Frame(main_pane, bg=BG_MID)
        main_pane.add(debate_frame, minsize=400)

        # Toolbar do visualizador de arquivos (oculta por padrão)
        self.viewer_toolbar = tk.Frame(debate_frame, bg=BG_LIGHT)

        self.btn_close_viewer = tk.Button(
            self.viewer_toolbar, text="✕ Fechar", font=("Segoe UI", 9, "bold"),
            bg=ACCENT_RED, fg=BG_DARK, relief=tk.FLAT, padx=10, pady=3,
            command=self._close_file_viewer, cursor="hand2"
        )
        self.btn_close_viewer.pack(side=tk.RIGHT, padx=(4, 8), pady=4)

        self.btn_open_file_dir = tk.Button(
            self.viewer_toolbar, text="📂 Abrir no Explorer", font=("Segoe UI", 9, "bold"),
            bg=BG_MID, fg=FG_PRIMARY, relief=tk.FLAT, padx=10, pady=3,
            command=self._open_file_folder, cursor="hand2"
        )
        self.btn_open_file_dir.pack(side=tk.RIGHT, padx=4, pady=4)

        self.btn_copy_file = tk.Button(
            self.viewer_toolbar, text="📋 Copiar Código", font=("Segoe UI", 9, "bold"),
            bg=ACCENT_BLUE, fg=BG_DARK, relief=tk.FLAT, padx=10, pady=3,
            command=self._copy_file_content, cursor="hand2"
        )
        self.btn_copy_file.pack(side=tk.RIGHT, padx=4, pady=4)

        self.viewer_title_label = tk.Label(
            self.viewer_toolbar, text="", fg=ACCENT_CYAN, bg=BG_LIGHT,
            font=("Segoe UI", 10, "bold"), anchor=tk.W
        )
        self.viewer_title_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 5), pady=4)

        self.debate_text = scrolledtext.ScrolledText(
            debate_frame, wrap=tk.WORD, font=("Consolas", 10),
            bg=BG_MID, fg=FG_PRIMARY, insertbackground=FG_PRIMARY,
            relief=tk.FLAT, highlightthickness=0, state=tk.DISABLED
        )
        self.debate_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Tags de cores
        self.debate_text.tag_configure("title", foreground=ACCENT_CYAN, font=("Consolas", 11, "bold"))
        self.debate_text.tag_configure("dim", foreground=FG_DIM)
        self.debate_text.tag_configure("separator", foreground=FG_DIM)
        self.debate_text.tag_configure("status_continue", foreground=STATUS_COLORS["CONTINUE"], font=("Consolas", 10, "bold"))
        self.debate_text.tag_configure("status_consensus", foreground=STATUS_COLORS["CONSENSUS"], font=("Consolas", 10, "bold"))
        self.debate_text.tag_configure("status_stop", foreground=STATUS_COLORS["STOP"], font=("Consolas", 10, "bold"))
        self.debate_text.tag_configure("error", foreground=ACCENT_RED, font=("Consolas", 10, "bold"))
        self.debate_text.tag_configure("loading", foreground=ACCENT_CYAN, font=("Consolas", 10, "italic"))

        for agent, color in AGENT_COLORS.items():
            self.debate_text.tag_configure(f"agent_{agent}", foreground=color, font=("Consolas", 10, "bold"))

        self.debate_text.tag_configure("argument", foreground=FG_PRIMARY)
        self.debate_text.tag_configure("header_blue", foreground=ACCENT_BLUE, font=("Consolas", 10, "bold"))
        self.debate_text.tag_configure("header_green", foreground=ACCENT_GREEN, font=("Consolas", 10, "bold"))
        self.debate_text.tag_configure("header_yellow", foreground=ACCENT_YELLOW, font=("Consolas", 10, "bold"))
        self.debate_text.tag_configure("system", foreground=ACCENT_MAGENTA, font=("Consolas", 9, "italic"))

        # Barra de status
        status_bar = ttk.Frame(self.root)
        status_bar.pack(fill=tk.X, padx=15, pady=(0, 10))

        self.status_label = ttk.Label(status_bar, text="Pronto", style="Status.TLabel")
        self.status_label.pack(side=tk.LEFT)

        self.progress_label = ttk.Label(status_bar, text="", style="Status.TLabel")
        self.progress_label.pack(side=tk.LEFT, padx=(20, 0))

        self.turn_label = ttk.Label(status_bar, text="", style="Status.TLabel")
        self.turn_label.pack(side=tk.RIGHT)

    def _on_mode_change(self):
        """Callback quando modo e alterado."""
        mode = self.mode_var.get()
        if mode == "autonomous":
            self.hours_entry.config(state=tk.NORMAL)
            self.topic_entry.config(state=tk.DISABLED)
            self.scenario_btn.config(state=tk.DISABLED)
        elif mode in ("engineering", "content"):
            self.hours_entry.config(state=tk.DISABLED)
            self.topic_entry.config(state=tk.NORMAL)
            self.scenario_btn.config(state=tk.NORMAL)
        else:
            self.hours_entry.config(state=tk.DISABLED)
            self.topic_entry.config(state=tk.NORMAL)
            self.scenario_btn.config(state=tk.NORMAL)

    def _fill_random_scenario(self):
        """Preenche o campo de tópico com um cenário rico de engenharia ou pauta de artigo."""
        mode = self.mode_var.get()
        try:
            from scenarios import get_scenario_engine
            engine = get_scenario_engine()
            if mode == "content":
                topic = engine.get_random_content_topic()
            else:
                sc = engine.get_random_engineering_scenario()
                topic = sc.prompt

            self.topic_entry.delete(0, tk.END)
            self.topic_entry.insert(0, topic)
            self._set_status("Cenário de produção carregado!", ACCENT_GREEN)
        except Exception as e:
            self._set_status(f"Erro ao carregar cenário: {e}", ACCENT_RED)

    def _open_output_folder(self):
        """Abre o diretório output/ no explorador de arquivos."""
        import os
        from pathlib import Path
        output_dir = (Path(__file__).resolve().parent / "output").resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(str(output_dir))
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(output_dir)])
        except Exception as e:
            messagebox.showinfo("Output", f"Arquivos salvos em:\n{output_dir}")

    def _load_debate_history(self):
        """Carrega historico de debates do banco em background."""
        def load():
            import asyncio as _asyncio
            loop = _asyncio.new_event_loop()
            _asyncio.set_event_loop(loop)
            try:
                from server import CortexDB
                debates = loop.run_until_complete(CortexDB.get_recent_debates(20))
                self.root.after(0, self._render_debate_history, debates)
            except Exception as e:
                self.root.after(0, lambda: self._append_system(f"Erro ao carregar historico: {e}"))
            finally:
                loop.close()

        threading.Thread(target=load, daemon=True).start()

    def _load_projects_history(self):
        """Carrega a lista de projetos e arquivos gerados em background."""
        def load():
            import urllib.request
            try:
                with urllib.request.urlopen("http://127.0.0.1:8000/api/teamwork/projects", timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    projects = data.get("projects", [])
                    self.root.after(0, self._render_projects_history, projects)
            except Exception:
                pass
        threading.Thread(target=load, daemon=True).start()

    def _render_projects_history(self, projects):
        """Renderiza os projetos e seus arquivos na aba Projetos da sidebar."""
        for widget in self.projects_inner.winfo_children():
            widget.destroy()
        self.project_entries.clear()

        if not projects:
            tk.Label(
                self.projects_inner, text="Nenhum projeto gerado ainda.\nInicie o TeamWork para criar código e artigos!",
                fg=FG_DIM, bg=BG_MID, font=("Segoe UI", 9), wraplength=220, justify=tk.CENTER
            ).pack(padx=10, pady=25)
            return

        for p in projects:
            p_name = p.get("project_name", p.get("session_id", "Projeto"))
            mode = p.get("mode", "engineering")
            goal = p.get("goal", p_name)
            files = p.get("files", [])
            date_str = p.get("created_at", "")[:16].replace("T", " ")
            icon = "⚙️" if mode == "engineering" else "✍️"

            card = tk.Frame(self.projects_inner, bg=BG_MID, relief=tk.FLAT)
            card.pack(fill=tk.X, padx=2, pady=3)

            header_lbl = tk.Label(
                card, text=f"{icon} {p_name}", fg=ACCENT_GREEN if mode == "engineering" else ACCENT_MAGENTA,
                bg=BG_MID, font=("Segoe UI", 9, "bold"), anchor=tk.W, wraplength=220, justify=tk.LEFT
            )
            header_lbl.pack(fill=tk.X, padx=6, pady=(4, 0))

            goal_lbl = tk.Label(
                card, text=goal[:45] + ("..." if len(goal) > 45 else ""),
                fg=FG_PRIMARY, bg=BG_MID, font=("Segoe UI", 8), anchor=tk.W, wraplength=220, justify=tk.LEFT
            )
            goal_lbl.pack(fill=tk.X, padx=6, pady=(0, 2))

            meta_lbl = tk.Label(
                card, text=f"  {date_str} | {len(files)} arquivo(s)", fg=FG_DIM, bg=BG_MID,
                font=("Segoe UI", 8), anchor=tk.W
            )
            meta_lbl.pack(fill=tk.X, padx=6, pady=(0, 4))

            # Lista de arquivos clicáveis
            files_frame = tk.Frame(card, bg=BG_DARK)
            files_frame.pack(fill=tk.X, padx=4, pady=(0, 4))

            for f in files:
                f_path = f.get("path") if isinstance(f, dict) else str(f)
                f_btn = tk.Label(
                    files_frame, text=f"  📄 {f_path}", fg=ACCENT_CYAN, bg=BG_DARK,
                    font=("Consolas", 8), anchor=tk.W, cursor="hand2"
                )
                f_btn.pack(fill=tk.X, padx=4, pady=1)

                def make_click_handler(proj=p_name, fpath=f_path):
                    return lambda e: self._show_file_content(proj, fpath)

                f_btn.bind("<Button-1>", make_click_handler(p_name, f_path))
                f_btn.bind("<Enter>", lambda e, b=f_btn: b.configure(fg=ACCENT_YELLOW))
                f_btn.bind("<Leave>", lambda e, b=f_btn: b.configure(fg=ACCENT_CYAN))

            sep = tk.Frame(self.projects_inner, bg=BG_LIGHT, height=1)
            sep.pack(fill=tk.X, padx=6, pady=2)

    def _show_file_content(self, project_id: str, file_path: str):
        """Carrega e exibe o conteúdo de um arquivo de projeto gerado no painel central."""
        def load():
            import urllib.request
            import urllib.parse
            url = f"http://127.0.0.1:8000/api/teamwork/file?project_id={urllib.parse.quote(project_id)}&file_path={urllib.parse.quote(file_path)}"
            try:
                with urllib.request.urlopen(url, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    content = data.get("content", "")

                    def render():
                        self.viewer_toolbar.pack(fill=tk.X, padx=2, pady=(2, 4), before=self.debate_text)
                        self.viewer_title_label.config(text=f"📄 {project_id} / {file_path}")
                        self.active_file_info = (project_id, file_path, content)

                        self.debate_text.config(state=tk.NORMAL)
                        self.debate_text.delete("1.0", tk.END)
                        self.debate_text.insert(tk.END, f"=== ARQUIVO: {file_path} ({project_id}) ===\n\n", "title")
                        self.debate_text.insert(tk.END, content, "argument")
                        self.debate_text.config(state=tk.DISABLED)
                        self._set_status(f"Visualizando: {file_path}", ACCENT_CYAN)

                    self.root.after(0, render)
            except Exception as e:
                self.root.after(0, lambda: self._set_status(f"Erro ao abrir arquivo: {e}", ACCENT_RED))

        threading.Thread(target=load, daemon=True).start()

    def _close_file_viewer(self):
        """Fecha o visualizador de arquivo e restaura o status."""
        self.viewer_toolbar.pack_forget()
        self._set_status("Pronto", ACCENT_GREEN)

    def _copy_file_content(self):
        """Copia o conteúdo do arquivo atualmente visualizado para a área de transferência."""
        if hasattr(self, "active_file_info") and self.active_file_info:
            content = self.active_file_info[2]
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self._set_status("Código copiado para a área de transferência!", ACCENT_GREEN)

    def _open_file_folder(self):
        """Abre a pasta do projeto no Windows Explorer."""
        if hasattr(self, "active_file_info") and self.active_file_info:
            import os
            from pathlib import Path
            proj_dir = (Path(__file__).resolve().parent / "output" / self.active_file_info[0]).resolve()
            proj_dir.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(proj_dir))

    def _load_knowledge_base(self):
        """Carrega topicos discutidos do banco em background."""
        def load():
            import asyncio as _asyncio
            loop = _asyncio.new_event_loop()
            _asyncio.set_event_loop(loop)
            try:
                from server import CortexDB
                topics = loop.run_until_complete(CortexDB.get_discussed_topics())
                self.root.after(0, self._render_knowledge_base, topics)
            except Exception as e:
                pass
            finally:
                loop.close()

        threading.Thread(target=load, daemon=True).start()

    def _render_knowledge_base(self, topics):
        """Renderiza a lista de topicos discutidos na sidebar."""
        for widget in self.knowledge_inner.winfo_children():
            widget.destroy()

        if not topics:
            tk.Label(
                self.knowledge_inner, text="Nenhum topico ainda", fg=FG_DIM, bg=BG_MID,
                font=("Segoe UI", 9), wraplength=220
            ).pack(padx=10, pady=10)
            return

        for topic in topics[:10]:
            topic_text = topic if isinstance(topic, str) else topic.get("topic", str(topic))
            tk.Label(
                self.knowledge_inner, text=f"• {topic_text[:40]}", fg=FG_PRIMARY, bg=BG_MID,
                font=("Segoe UI", 9), anchor=tk.W, wraplength=220
            ).pack(fill=tk.X, padx=10, pady=1)

    def _render_debate_history(self, debates):
        """Renderiza a lista de debates na sidebar."""
        # Limpar entradas anteriores
        for widget in self.sidebar_inner.winfo_children():
            widget.destroy()
        self.debate_entries.clear()
        self.debate_ids.clear()

        if not debates:
            tk.Label(
                self.sidebar_inner, text="Nenhum debate encontrado", fg=FG_DIM, bg=BG_MID,
                font=("Segoe UI", 9), wraplength=220
            ).pack(padx=10, pady=20)
            return

        for i, debate in enumerate(debates):
            self._add_debate_entry(debate, i)

    def _add_debate_entry(self, debate, index):
        """Adiciona uma entrada de debate na sidebar."""
        topic = debate.get("topic", "Sem topico")
        created_at = debate.get("created_at", "")
        total_turns = debate.get("total_turns", 0)
        last_status = debate.get("last_status", "N/A")
        conv_id = debate.get("id", "")

        # Formatar data
        if created_at:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(created_at)
                date_str = dt.strftime("%d/%m %H:%M")
            except (ValueError, TypeError):
                date_str = created_at[:16]
        else:
            date_str = "?"

        # Cor do status
        if last_status == "CONSENSUS":
            status_color = ACCENT_GREEN
            status_icon = "✓"
        elif last_status == "CONTINUE":
            status_color = ACCENT_YELLOW
            status_icon = "…"
        else:
            status_color = FG_DIM
            status_icon = "•"

        # Frame da entrada
        entry_frame = tk.Frame(self.sidebar_inner, bg=BG_MID, cursor="hand2")
        entry_frame.pack(fill=tk.X, padx=2, pady=1)

        # Topico (truncado)
        topic_display = topic[:35] + "..." if len(topic) > 35 else topic
        topic_label = tk.Label(
            entry_frame, text=f"{status_icon} {topic_display}", fg=FG_PRIMARY, bg=BG_MID,
            font=("Segoe UI", 9), anchor=tk.W, wraplength=220, justify=tk.LEFT
        )
        topic_label.pack(fill=tk.X, padx=8, pady=(4, 0))

        # Info linha
        info_label = tk.Label(
            entry_frame, text=f"  {date_str} | {total_turns} turnos", fg=FG_DIM, bg=BG_MID,
            font=("Segoe UI", 8), anchor=tk.W
        )
        info_label.pack(fill=tk.X, padx=8, pady=(0, 4))

        # Separador
        sep = tk.Frame(self.sidebar_inner, bg=BG_LIGHT, height=1)
        sep.pack(fill=tk.X, padx=8, pady=1)

        # Armazenar referencia
        self.debate_entries.append(entry_frame)
        self.debate_ids.append(conv_id)

        # Bind click
        def on_click(e, cid=conv_id, t=topic):
            self._show_debate_detail(cid, t)

        for widget in [entry_frame, topic_label, info_label]:
            widget.bind("<Button-1>", on_click)
            widget.bind("<Enter>", lambda e, f=entry_frame: f.configure(bg=BG_LIGHT))
            widget.bind("<Leave>", lambda e, f=entry_frame: f.configure(bg=BG_MID))

    def _show_debate_detail(self, conversation_id, topic):
        """Mostra detalhes de um debate na area principal."""
        def load():
            import asyncio as _asyncio
            loop = _asyncio.new_event_loop()
            _asyncio.set_event_loop(loop)
            try:
                from server import CortexDB
                messages = loop.run_until_complete(CortexDB.get_debate_messages(conversation_id))
                self.root.after(0, self._render_debate_detail, topic, messages)
            except Exception as e:
                self.root.after(0, lambda: self._append_system(f"Erro ao carregar debate: {e}"))
            finally:
                loop.close()

        self._set_status(f"Carregando: {topic[:40]}...", ACCENT_BLUE)
        threading.Thread(target=load, daemon=True).start()

    def _render_debate_detail(self, topic, messages):
        """Renderiza detalhes de um debate na area de texto."""
        self.debate_text.config(state=tk.NORMAL)
        self.debate_text.delete("1.0", tk.END)

        self._append_text(f"\n{'='*70}\n", "separator")
        self._append_text(f"  DEBATE: {topic}\n", "title")
        self._append_text(f"  Total de turnos: {len(messages)}\n", "dim")
        self._append_text(f"{'='*70}\n\n", "separator")

        for msg in messages:
            agent = msg.get("agent", "?")
            content = msg.get("content", "")
            status = msg.get("status", "?")
            turn = msg.get("turn", "?")
            tag = f"agent_{agent}" if agent in AGENT_COLORS else "argument"
            status_tag = f"status_{status.lower()}" if status.lower() in STATUS_COLORS else "dim"

            self._append_text(f"  Turno {turn} — ", "dim")
            self._append_text(f"{agent}\n", tag)
            self._append_text(f"  {content}\n", "argument")
            self._append_text(f"  [{status}]\n", status_tag)
            self._append_text(f"  {'─'*70}\n", "separator")

        self._set_status(f"Debate: {topic[:50]}", ACCENT_GREEN)
        self.debate_text.config(state=tk.DISABLED)

    def _start_server(self):
        """Inicia o servidor em background."""
        import uvicorn
        from server import app

        def run():
            uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

        self._set_status("Iniciando servidor...", ACCENT_YELLOW)
        self.root.after(1500, self._check_server)

    def _check_server(self):
        """Verifica se o servidor esta rodando."""
        import urllib.request
        try:
            req = urllib.request.urlopen("http://127.0.0.1:8000/docs", timeout=2)
            if req.status == 200:
                self.server_running = True
                self.server_status.config(text="● Servidor online", fg=ACCENT_GREEN)
                self._set_status("Servidor online. Conectando...", ACCENT_GREEN)
                self._connect_ws()
                return
        except Exception:
            pass
        self._set_status("Aguardando servidor...", ACCENT_YELLOW)
        self.root.after(1000, self._check_server)

    def _connect_ws(self):
        """Conecta ao WebSocket do servidor."""
        def connect():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self._ws_loop())

        self.thread = threading.Thread(target=connect, daemon=True)
        self.thread.start()

    async def _ws_loop(self):
        """Loop WebSocket."""
        try:
            async with websockets.connect(URI) as ws:
                self.ws = ws
                self.connected = True
                self.root.after(0, lambda: self.server_status.config(text="● Conectado", fg=ACCENT_GREEN))
                self.root.after(0, lambda: self._set_status("Pronto para debate", ACCENT_GREEN))
                self.root.after(0, lambda: self._append_system("Conectado ao servidor. Pronto para iniciar debate."))
                self.root.after(100, self._load_debate_history)
                self.root.after(200, self._load_knowledge_base)
                self.root.after(300, self._load_projects_history)

                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=0.5)
                        event = json.loads(raw)
                        self.root.after(0, self._handle_event, event)
                    except asyncio.TimeoutError:
                        continue
                    except websockets.exceptions.ConnectionClosed:
                        self.root.after(0, lambda: self._append_system("Conexao WebSocket encerrada."))
                        break
        except Exception as e:
            self.root.after(0, lambda: self.server_status.config(text=f"● Erro: {e}", fg=ACCENT_RED))
            self.root.after(0, lambda: self._set_status(f"Erro de conexao: {e}", ACCENT_RED))

    def _start_debate(self):
        """Inicia um debate."""
        if not self.connected:
            messagebox.showwarning("Aviso", "Aguardando conexao com o servidor...")
            return

        if self.running:
            return

        mode = self.mode_var.get()
        topic = self.topic_entry.get().strip()
        turns = self.turns_var.get().strip()
        model = self.model_var.get().strip()
        hours = self.hours_var.get().strip()

        if mode == "single" and not topic:
            messagebox.showwarning("Aviso", "Digite um topico para o debate.")
            return

        self.running = True
        self.current_mode = mode
        self.current_turn = 0
        self.max_turns = int(turns) if turns.isdigit() else 48
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

        # Limpar area de debate
        self.debate_text.config(state=tk.NORMAL)
        self.debate_text.delete("1.0", tk.END)
        self.debate_text.config(state=tk.DISABLED)

        # Enviar payload
        if mode in ("engineering", "content"):
            self._set_status(f"Iniciando TeamWork ({mode})...", ACCENT_GREEN)
            self._append_system(f"Modo TEAMWORK ({mode.upper()}) | Objetivo: {topic}")
            self._run_teamwork_pipeline(mode, topic, model)
            return

        elif mode == "single":
            payload = {
                "mode": "single",
                "topic": topic,
                "max_turns": self.max_turns,
                "num_ctx": 8192,
                "model": None if model == "auto" else model
            }
            self._set_status(f"Iniciando debate: {topic[:50]}...", ACCENT_BLUE)
            self._append_system(f"Modo SINGLE | Topico: {topic} | Turnos: {self.max_turns}")
        else:
            payload = {
                "mode": "autonomous",
                "duration_hours": float(hours) if hours.replace(".", "").isdigit() else 8.0,
                "num_ctx": 8192,
                "model": None if model == "auto" else model
            }
            self._set_status(f"Iniciando sessao autonoma ({hours}h)...", ACCENT_YELLOW)
            self._append_system(f"Modo AUTONOMO | Duracao: {hours}h | Turnos/debate: {self.max_turns}")

        def send():
            if self.loop and self.ws:
                asyncio.run_coroutine_threadsafe(self.ws.send(json.dumps(payload)), self.loop)

        threading.Thread(target=send, daemon=True).start()
        self._start_loading("Enviando payload ao servidor...")
        self._update_progress()

    def _run_teamwork_pipeline(self, mode: str, goal: str, model: str):
        """Executa a pipeline de Teamwork via streaming SSE e atualiza a interface em tempo real."""
        def worker():
            self.root.after(0, lambda: self._start_loading(f"Iniciando TeamWork ({mode})..."))
            self.root.after(0, lambda: self._append_text(f"\n{'='*70}\n", "separator"))
            self.root.after(0, lambda: self._append_text(f"  🚀 SESSÃO DE TEAMWORK INICIADA ({mode.upper()})\n", "header_green"))
            self.root.after(0, lambda: self._append_text(f"  Objetivo: {goal}\n", "dim"))
            self.root.after(0, lambda: self._append_text(f"{'='*70}\n\n", "separator"))

            try:
                import urllib.request
                req_data = json.dumps({
                    "mode": mode,
                    "goal": goal,
                    "model": None if model == "auto" else model
                }).encode("utf-8")

                req = urllib.request.Request(
                    "http://127.0.0.1:8000/api/teamwork/stream",
                    data=req_data,
                    headers={"Content-Type": "application/json"}
                )

                with urllib.request.urlopen(req, timeout=600) as response:
                    for raw_line in response:
                        line = raw_line.decode("utf-8").strip()
                        if not line.startswith("data:"):
                            continue
                        json_str = line[5:].strip()
                        if not json_str:
                            continue
                        evt = json.loads(json_str)

                        evt_type = evt.get("type", "")
                        status = evt.get("status", "")
                        msg = evt.get("message", "")
                        step_data = evt.get("step_data") or {}

                        if status == "started":
                            self.root.after(0, lambda m=msg: self._set_status(m, ACCENT_CYAN))

                        elif status == "model_fallback":
                            def on_fallback(m=msg):
                                self._append_text(f"\n  ⚡ [CIRCUIT BREAKER] {m}\n", "header_yellow")
                                self._set_status(m, ACCENT_YELLOW)
                            self.root.after(0, on_fallback)

                        elif status == "running":
                            role = evt.get("role", "")
                            def on_step_start(r=role, m=msg):
                                self._start_loading(f"{r}: {m}")
                                self._set_status(m, ACCENT_YELLOW)
                                self._append_text(f"\n  ⏳ [{r}] Iniciando análise e elaborando arquivos...\n", "dim")
                            self.root.after(0, on_step_start)

                        elif status == "completed":
                            role = evt.get("role", "Especialista")
                            role_title = step_data.get("role_title", role)
                            stage = evt.get("stage", "")
                            contrib = step_data.get("contribution", "")
                            files = step_data.get("files", [])
                            step_num = step_data.get("step_number", 1)
                            total = step_data.get("total_steps", 6 if mode == "content" else 7)

                            def on_step_done(r_title=role_title, st=stage, c=contrib, fls=files, s_n=step_num, tot=total):
                                self._append_text(f"\n  👤 {r_title} [{st}] (Etapa {s_n}/{tot}):\n", "header_blue")
                                self._append_text(f"  {c}\n", "argument")
                                if fls:
                                    self._append_text(f"  📁 Arquivos gerados:\n", "dim")
                                    for f in fls:
                                        self._append_text(f"     - {f}\n", "header_green")
                                self._append_text(f"  {'─'*70}\n", "separator")
                                pct = int((s_n / tot) * 100)
                                self.progress_label.config(text=f"Etapa {s_n}/{tot} ({pct}%)")
                                self._set_status(f"Etapa {s_n}/{tot} concluída por {r_title}", ACCENT_GREEN)
                                self._load_projects_history()

                            self.root.after(0, on_step_done)

                        elif evt_type == "teamwork_complete":
                            res = evt.get("result", {})
                            out_dir = res.get("output_directory", "")
                            summary = res.get("executive_summary", "")

                            def on_finish(o=out_dir, sm=summary):
                                self._stop_loading()
                                self._append_text(f"\n{'='*70}\n", "separator")
                                self._append_text(f"  ✅ TEAMWORK CONCLUÍDO COM SUCESSO!\n", "header_green")
                                self._append_text(f"  {sm}\n\n", "argument")
                                self._append_text(f"  📦 Arquivos salvos em: {o}\n", "title")
                                self._append_text(f"{'='*70}\n\n", "separator")
                                self._set_status("Teamwork finalizado com sucesso!", ACCENT_GREEN)
                                self.running = False
                                self.start_btn.config(state=tk.NORMAL)
                                self.stop_btn.config(state=tk.DISABLED)
                                self._load_projects_history()

                            self.root.after(0, on_finish)

                        elif evt_type == "error":
                            def on_error(err_m=msg or evt.get("message", "Erro desconhecido")):
                                self._stop_loading()
                                self._append_text(f"\n  ❌ ERRO: {err_m}\n\n", "error")
                                self._set_status(f"Erro: {err_m}", ACCENT_RED)
                                self.running = False
                                self.start_btn.config(state=tk.NORMAL)
                                self.stop_btn.config(state=tk.DISABLED)

                            self.root.after(0, on_error)

            except Exception as e:
                def err(err_msg=str(e)):
                    self._stop_loading()
                    self._append_text(f"\n  ❌ ERRO DE CONEXÃO NO TEAMWORK: {err_msg}\n\n", "error")
                    self._set_status(f"Erro: {err_msg}", ACCENT_RED)
                    self.running = False
                    self.start_btn.config(state=tk.NORMAL)
                    self.stop_btn.config(state=tk.DISABLED)

                self.root.after(0, err)

                self.root.after(0, err)

        threading.Thread(target=worker, daemon=True).start()

    def _stop_debate(self):
        """Para o debate atual."""
        self.running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self._stop_loading()
        self._set_status("Parado pelo usuario", ACCENT_RED)
        self._append_text("\n  ■ Debate interrompido pelo usuario\n\n", "error")

    def _handle_event(self, event):
        """Processa um evento recebido do servidor."""
        evt = event.get("event")
        data = event.get("data", {})

        if evt == "session_start":
            self._stop_loading()
            self._append_text(f"\n{'='*70}\n", "separator")
            self._append_text(f"  SESSAO INICIADA\n", "header_blue")
            self._append_text(f"  ID: {data.get('session_id', '?')}\n", "dim")
            self._append_text(f"  Duracao: {data.get('duration_hours', '?')}h\n", "dim")
            self._append_text(f"  Modelo: {data.get('model', '?')}\n", "dim")
            self._append_text(f"{'='*70}\n\n", "separator")
            self._set_status("Sessao autonoma em andamento...", ACCENT_YELLOW)

        elif evt == "debate_start":
            self._stop_loading()
            num = data.get("debate_num", "?")
            topic = data.get("topic") or "?"
            self._append_text(f"\n  DEBATE {num}: {topic}\n", "title")
            self._append_text(f"  {'─'*70}\n", "separator")
            self._set_status(f"Debate {num}: {topic[:40] if topic else '?'}...", ACCENT_CYAN)

        elif evt == "turn_start":
            agent = data.get("agent", "?")
            turn = data.get("turn", "?")
            self.current_turn = turn
            tag = f"agent_{agent}" if agent in AGENT_COLORS else "dim"
            self._append_text(f"\n  Turno {turn} — ", "dim")
            self._append_text(f"{agent}...\n", tag)
            self._set_status(f"Turno {turn}/{self.max_turns} — {agent} analisando...", ACCENT_CYAN)
            self._start_loading(f"{agent} gerando argumento...")
            self._update_progress()

        elif evt == "turn_end":
            self._stop_loading()
            agent = data.get("agent", "?")
            turn = data.get("turn", self.current_turn)
            arg = data.get("argument", "Sem conteudo.")
            status = data.get("status", "?")
            tag = f"agent_{agent}" if agent in AGENT_COLORS else "argument"
            status_tag = f"status_{status.lower()}" if status.lower() in STATUS_COLORS else "dim"

            self._append_text(f"\n  {agent}:\n", tag)
            self._append_text(f"  {arg}\n", "argument")
            self._append_text(f"  [{status}]\n", status_tag)
            self._append_text(f"  {'─'*70}\n", "separator")

            self._set_status(f"Turno {turn}/{self.max_turns} — {status}", STATUS_COLORS.get(status, FG_DIM))
            self._update_progress()

        elif evt == "debate_complete":
            self._stop_loading()
            reason = data.get("reason", "?")
            message = data.get("message", "")
            summary = data.get("summary", "")

            if reason == "topic_exhausted":
                motivo = "Topico Exaurido"
                tag = "header_red"
                self._append_text(f"\n  ⚠ {motivo}\n", tag)
                if message:
                    self._append_text(f"  {message}\n", "dim")
                self._set_status(f"Topico exaurido — escolha outro topico", ACCENT_RED)
                self.running = False
                self.start_btn.config(state=tk.NORMAL)
                self.stop_btn.config(state=tk.DISABLED)
            else:
                motivo = "Consenso" if reason == "consensus" else "Timeout"
                tag = "header_green" if reason == "consensus" else "header_yellow"
                self._append_text(f"\n  DEBATE ENCERRADO — {motivo} | Turnos: {data.get('total_turns', '?')}\n", tag)
                self._append_text(f"{'='*70}\n\n", "separator")

                # Exibir resumo do debate
                if summary:
                    self._append_text(f"\n  RESUMO DO DEBATE:\n", "header_blue")
                    for line in summary.split("\n"):
                        self._append_text(f"  {line}\n", "argument")
                    self._append_text(f"\n{'='*70}\n\n", "separator")

                self._set_status(f"Debate encerrado: {motivo}", ACCENT_GREEN if reason == "consensus" else ACCENT_YELLOW)
                # No modo autonomous, nao para — espera proximo debate
                if self.current_mode == "single":
                    self.running = False
                    self.start_btn.config(state=tk.NORMAL)
                    self.stop_btn.config(state=tk.DISABLED)

        elif evt == "debate_paused":
            duration = data.get("duration_seconds", 60)
            next_debate = data.get("next_debate", "?")
            self._append_text(f"\n  ⏸ PAUSA — Proximo debate em {duration}s...\n", "header_yellow")
            self._set_status(f"Pausa {duration}s — Proximo debate: {next_debate}", ACCENT_YELLOW)
            self._start_loading(f"Aguardando {duration}s para proximo debate...")
            self._start_pause_countdown(duration)

        elif evt == "session_complete":
            self._stop_loading()
            self._append_text(f"\n{'='*70}\n", "separator")
            self._append_text(f"  SESSAO ENCERRADA\n", "header_yellow")
            self._append_text(f"  Total de debates: {data.get('total_debates', '?')}\n", "dim")
            self._append_text(f"  Duracao: {data.get('duration_hours', '?')}h\n", "dim")
            self._append_text(f"\n  Topicos discutidos:\n", "argument")
            for i, t in enumerate(data.get("topics", []), 1):
                self._append_text(f"    {i}. {t}\n", "dim")
            summary = data.get("summary", "N/A")
            if summary:
                self._append_text(f"\n  Resumo:\n", "argument")
                self._append_text(f"  {summary}\n", "dim")
            self._append_text(f"{'='*70}\n\n", "separator")
            self.running = False
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self._set_status("Sessao encerrada", ACCENT_GREEN)

        elif evt == "error":
            self._stop_loading()
            self._append_text(f"\n  ERRO: {data.get('message', '?')}\n\n", "error")
            self.running = False
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self._set_status(f"Erro: {data.get('message', '?')}", ACCENT_RED)

    def _start_loading(self, message="Processando..."):
        """Inicia animacao de loading com cronometro."""
        import time
        self.loading_active = True
        self.loading_message = message
        self.step_start_time = time.time()
        self._animate_loading()

    def _stop_loading(self):
        """Para animacao de loading."""
        self.loading_active = False
        self.step_start_time = 0.0
        self.loading_frame_label.config(text="")

    def _animate_loading(self):
        """Anima o indicador de loading com tempo decorrido."""
        if not self.loading_active:
            return
        import time
        self.loading_frame = (self.loading_frame + 1) % len(LOADING_FRAMES)
        frame = LOADING_FRAMES[self.loading_frame]
        elapsed = int(time.time() - self.step_start_time) if self.step_start_time > 0 else 0
        self.loading_frame_label.config(text=f"  {frame} {self.loading_message} (⏱ {elapsed}s)")
        self.root.after(100, self._animate_loading)

    def _start_pause_countdown(self, duration):
        """Inicia countdown da pausa na barra de status."""
        self.pause_remaining = duration
        self._update_pause_countdown()

    def _update_pause_countdown(self):
        """Atualiza countdown da pausa."""
        if self.pause_remaining <= 0:
            self._set_status("Iniciando proximo debate...", ACCENT_GREEN)
            return
        mins = self.pause_remaining // 60
        secs = self.pause_remaining % 60
        time_str = f"{mins:02d}:{secs:02d}" if mins > 0 else f"{secs}s"
        self._set_status(f"Pausa — proximo debate em {time_str}", ACCENT_YELLOW)
        self.pause_remaining -= 1
        self.root.after(1000, self._update_pause_countdown)

    def _set_status(self, text, color=None):
        """Atualiza barra de status."""
        self.status_label.config(text=text)
        if color:
            self.status_label.config(foreground=color)

    def _update_progress(self):
        """Atualiza indicador de progresso."""
        if self.current_turn > 0:
            pct = int((self.current_turn / self.max_turns) * 100)
            bar_len = 20
            filled = int(bar_len * self.current_turn / self.max_turns)
            bar = "█" * filled + "░" * (bar_len - filled)
            self.progress_label.config(text=f"[{bar}] {pct}%")
            self.turn_label.config(text=f"Turno {self.current_turn}/{self.max_turns}")

    def _append_text(self, text, tag=None):
        """Adiciona texto a area de debate."""
        self.debate_text.config(state=tk.NORMAL)
        if tag:
            self.debate_text.insert(tk.END, text, tag)
        else:
            self.debate_text.insert(tk.END, text)
        self.debate_text.see(tk.END)
        self.debate_text.config(state=tk.DISABLED)

    def _append_system(self, text):
        """Adiciona mensagem de sistema."""
        self._append_text(f"  [SYS] {text}\n", "system")

    def run(self):
        """Inicia a aplicacao."""
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        """Trata o fechamento da janela."""
        self.running = False
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.root.destroy()


if __name__ == "__main__":
    app = THZMainsApp()
    app.run()

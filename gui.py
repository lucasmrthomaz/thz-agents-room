"""
THZ Minds — Interface Tkinter
Motor Multiagente Local com 8 LLMs
"""

import asyncio
import json
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
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
}

# Animacao de loading
LOADING_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class THZMainsApp:
    """Aplicacao principal THZ Minds."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("THZ Minds — Motor Multiagente Local")
        self.root.geometry("1000x750")
        self.root.minsize(800, 550)
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
        self.style.configure("Loading.TLabel", font=("Consolas", 12), foreground=ACCENT_CYAN)

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

        # Controles
        controls = ttk.Frame(self.root)
        controls.pack(fill=tk.X, padx=15, pady=5)

        # Modo
        mode_frame = ttk.Frame(controls)
        mode_frame.pack(side=tk.LEFT, padx=(0, 15))

        ttk.Label(mode_frame, text="Modo:").pack(side=tk.LEFT, padx=(0, 5))

        self.mode_var = tk.StringVar(value="single")
        self.btn_single = tk.Radiobutton(
            mode_frame, text="Single", variable=self.mode_var, value="single",
            bg=BG_DARK, fg=ACCENT_BLUE, selectcolor=BG_MID, activebackground=BG_DARK,
            activeforeground=ACCENT_BLUE, font=("Segoe UI", 10), command=self._on_mode_change
        )
        self.btn_single.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_autonomous = tk.Radiobutton(
            mode_frame, text="Autonomous", variable=self.mode_var, value="autonomous",
            bg=BG_DARK, fg=ACCENT_YELLOW, selectcolor=BG_MID, activebackground=BG_DARK,
            activeforeground=ACCENT_YELLOW, font=("Segoe UI", 10), command=self._on_mode_change
        )
        self.btn_autonomous.pack(side=tk.LEFT)

        # Topico
        topic_frame = ttk.Frame(controls)
        topic_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Label(topic_frame, text="Topico:").pack(side=tk.LEFT, padx=(0, 5))

        self.topic_entry = tk.Entry(
            topic_frame, font=("Segoe UI", 11), bg=BG_MID, fg=FG_PRIMARY,
            insertbackground=FG_PRIMARY, relief=tk.FLAT, highlightthickness=1,
            highlightbackground=FG_DIM, highlightcolor=ACCENT_BLUE
        )
        self.topic_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.topic_entry.bind("<Return>", lambda e: self._start_debate())

        # Botoes
        btn_frame = ttk.Frame(controls)
        btn_frame.pack(side=tk.RIGHT)

        self.start_btn = tk.Button(
            btn_frame, text="▶ Iniciar", font=("Segoe UI", 10, "bold"),
            bg=ACCENT_GREEN, fg=BG_DARK, relief=tk.FLAT, padx=15, pady=5,
            command=self._start_debate, state=tk.NORMAL
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.stop_btn = tk.Button(
            btn_frame, text="■ Parar", font=("Segoe UI", 10, "bold"),
            bg=ACCENT_RED, fg=BG_DARK, relief=tk.FLAT, padx=15, pady=5,
            command=self._stop_debate, state=tk.DISABLED
        )
        self.stop_btn.pack(side=tk.LEFT)

        # Configuracoes (linha)
        config_frame = ttk.Frame(self.root)
        config_frame.pack(fill=tk.X, padx=15, pady=(0, 5))

        ttk.Label(config_frame, text="Turnos:").pack(side=tk.LEFT, padx=(0, 3))
        self.turns_var = tk.StringVar(value="48")
        self.turns_entry = tk.Entry(
            config_frame, textvariable=self.turns_var, width=5,
            font=("Consolas", 10), bg=BG_MID, fg=FG_PRIMARY, relief=tk.FLAT,
            highlightthickness=1, highlightbackground=FG_DIM
        )
        self.turns_entry.pack(side=tk.LEFT, padx=(0, 15))

        ttk.Label(config_frame, text="Modelo:").pack(side=tk.LEFT, padx=(0, 3))
        self.model_var = tk.StringVar(value="auto")
        self.model_entry = tk.Entry(
            config_frame, textvariable=self.model_var, width=20,
            font=("Consolas", 10), bg=BG_MID, fg=FG_PRIMARY, relief=tk.FLAT,
            highlightthickness=1, highlightbackground=FG_DIM
        )
        self.model_entry.pack(side=tk.LEFT, padx=(0, 15))

        ttk.Label(config_frame, text="Duracao (h):").pack(side=tk.LEFT, padx=(0, 3))
        self.hours_var = tk.StringVar(value="8")
        self.hours_entry = tk.Entry(
            config_frame, textvariable=self.hours_var, width=5,
            font=("Consolas", 10), bg=BG_MID, fg=FG_PRIMARY, relief=tk.FLAT,
            highlightthickness=1, highlightbackground=FG_DIM
        )
        self.hours_entry.pack(side=tk.LEFT, padx=(0, 15))
        self.hours_entry.config(state=tk.DISABLED)

        # Separator
        ttk.Separator(self.root, orient="horizontal").pack(fill=tk.X, padx=15, pady=5)

        # Loading indicator
        self.loading_frame_label = tk.Label(
            self.root, text="", fg=ACCENT_CYAN, bg=BG_DARK,
            font=("Consolas", 12), anchor=tk.W
        )
        self.loading_frame_label.pack(fill=tk.X, padx=15, pady=(0, 2))

        # Area de debate
        debate_frame = ttk.Frame(self.root)
        debate_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 5))

        self.debate_text = scrolledtext.ScrolledText(
            debate_frame, wrap=tk.WORD, font=("Consolas", 10),
            bg=BG_MID, fg=FG_PRIMARY, insertbackground=FG_PRIMARY,
            relief=tk.FLAT, highlightthickness=0, state=tk.DISABLED
        )
        self.debate_text.pack(fill=tk.BOTH, expand=True)

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
        else:
            self.hours_entry.config(state=tk.DISABLED)
            self.topic_entry.config(state=tk.NORMAL)

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
        if mode == "single":
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
            topic = data.get("topic", "?")
            self._append_text(f"\n  DEBATE {num}: {topic}\n", "title")
            self._append_text(f"  {'─'*70}\n", "separator")
            self._set_status(f"Debate {num}: {topic[:40]}...", ACCENT_CYAN)

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
            motivo = "Consenso" if reason == "consensus" else "Timeout"
            tag = "header_green" if reason == "consensus" else "header_yellow"
            self._append_text(f"\n  DEBATE ENCERRADO — {motivo} | Turnos: {data.get('total_turns', '?')}\n", tag)
            self._append_text(f"{'='*70}\n\n", "separator")
            self.running = False
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self._set_status(f"Debate encerrado: {motivo}", ACCENT_GREEN if reason == "consensus" else ACCENT_YELLOW)

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
        """Inicia animacao de loading."""
        self.loading_active = True
        self.loading_message = message
        self._animate_loading()

    def _stop_loading(self):
        """Para animacao de loading."""
        self.loading_active = False
        self.loading_frame_label.config(text="")

    def _animate_loading(self):
        """Anima o indicador de loading."""
        if not self.loading_active:
            return
        self.loading_frame = (self.loading_frame + 1) % len(LOADING_FRAMES)
        frame = LOADING_FRAMES[self.loading_frame]
        self.loading_frame_label.config(text=f"  {frame} {self.loading_message}")
        self.root.after(100, self._animate_loading)

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

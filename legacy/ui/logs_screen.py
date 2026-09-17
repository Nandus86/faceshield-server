import tkinter as tk
from tkinter import font, scrolledtext
from utils.logger import get_recent_logs

class LogsScreen:
    """Screen to view detection logs."""
    
    def __init__(self, root, on_back):
        self.root = root
        self.on_back = on_back
        
        self.frame = tk.Frame(root, bg="#1e1e2e")
        self.create_widgets()
    
    def create_widgets(self):
        """Create logs viewer UI elements."""
        # Title
        title_font = font.Font(family="Arial", size=24, weight="bold")
        title = tk.Label(
            self.frame,
            text="Histórico de Detecções",
            font=title_font,
            bg="#1e1e2e",
            fg="#cdd6f4"
        )
        title.pack(pady=20)
        
        # Log display
        log_frame = tk.Frame(self.frame, bg="#1e1e2e")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=10)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            font=("Courier New", 11),
            bg="#181825",
            fg="#cdd6f4",
            relief=tk.FLAT,
            borderwidth=2
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Button frame
        button_frame = tk.Frame(self.frame, bg="#1e1e2e")
        button_frame.pack(pady=20)
        
        # Refresh button
        self.refresh_btn = tk.Button(
            button_frame,
            text="🔄 Atualizar",
            command=self.load_logs,
            font=("Arial", 12, "bold"),
            bg="#89b4fa",
            fg="#1e1e2e",
            activebackground="#74c7ec",
            relief=tk.FLAT,
            width=15,
            height=2,
            cursor="hand2"
        )
        self.refresh_btn.grid(row=0, column=0, padx=10)
        
        # Back button
        self.back_btn = tk.Button(
            button_frame,
            text="🔙 Voltar ao Menu",
            command=self.on_back,
            font=("Arial", 12, "bold"),
            bg="#6c7086",
            fg="#cdd6f4",
            activebackground="#585b70",
            relief=tk.FLAT,
            width=15,
            height=2,
            cursor="hand2"
        )
        self.back_btn.grid(row=0, column=1, padx=10)
        
        # Status label
        self.status_label = tk.Label(
            self.frame,
            text="",
            font=("Arial", 11),
            bg="#1e1e2e",
            fg="#a6adc8"
        )
        self.status_label.pack(pady=10)
    
    def load_logs(self):
        """Load and display all logs."""
        import os
        import config
        
        self.log_text.delete(1.0, tk.END)
        
        if not os.path.exists(config.LOG_FILE):
            self.log_text.insert(tk.END, "Nenhum log encontrado.\n")
            self.status_label.config(text="Nenhum registro disponível")
            return
        
        try:
            with open(config.LOG_FILE, "r", encoding="utf-8") as f:
                logs = f.readlines()
            
            if not logs:
                self.log_text.insert(tk.END, "Nenhum log encontrado.\n")
                self.status_label.config(text="Nenhum registro disponível")
            else:
                self.log_text.insert(tk.END, "".join(logs))
                self.status_label.config(text=f"Total de {len(logs)} detecções registradas")
        except Exception as e:
            self.log_text.insert(tk.END, f"Erro ao carregar logs: {e}\n")
            self.status_label.config(text="Erro ao carregar logs")
    
    def show(self):
        """Display this screen."""
        self.frame.pack(fill=tk.BOTH, expand=True)
        self.load_logs()
    
    def hide(self):
        """Hide this screen."""
        self.frame.pack_forget()

import tkinter as tk
from tkinter import font, scrolledtext, ttk
from datetime import datetime
import config
from core.presence_tracker import PresenceTracker
from ai_agent.agent import agent as ai_agent

class AnalyticsScreen:
    """Analytics and AI insights dashboard."""
    
    def __init__(self, root, on_back):
        self.root = root
        self.on_back = on_back
        self.tracker = PresenceTracker()
        
        self.frame = tk.Frame(root, bg="#1e1e2e")
        self.create_widgets()
    
    def create_widgets(self):
        """Create analytics UI elements."""
        # Title
        title_font = font.Font(family="Arial", size=24, weight="bold")
        title = tk.Label(
            self.frame,
            text="📊 Analytics & AI Insights",
            font=title_font,
            bg="#1e1e2e",
            fg="#cdd6f4"
        )
        title.pack(pady=20)
        
        # Main content
        content_frame = tk.Frame(self.frame, bg="#1e1e2e")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=40)
        
        # Left side - Statistics
        left_frame = tk.Frame(content_frame, bg="#1e1e2e")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        stats_title = tk.Label(
            left_frame,
            text="Estatísticas em Tempo Real",
            font=("Arial", 16, "bold"),
            bg="#1e1e2e",
            fg="#cdd6f4"
        )
        stats_title.pack(pady=(0, 15))
        
        # Statistics cards
        self.stats_frame = tk.Frame(left_frame, bg="#1e1e2e")
        self.stats_frame.pack(fill=tk.BOTH, expand=True)
        
        self.stat_labels = {}
        stats = [
            ("active", "👥 Pessoas Presentes", "#89b4fa"),
            ("today", "📅 Detectadas Hoje", "#a6e3a1"),
            ("registered", "✅ Cadastradas Hoje", "#f9e2af"),
            ("unknown", "⚠️ Desconhecidas Hoje", "#f38ba8"),
            ("avg_time", "⏱️ Tempo Médio", "#cba6f7")
        ]
        
        for key, label, color in stats:
            card = self.create_stat_card(label, "0", color)
            card.pack(fill=tk.X, pady=5)
            self.stat_labels[key] = card
        
        # Active people list
        active_title = tk.Label(
            left_frame,
            text="Pessoas Atualmente Presentes",
            font=("Arial", 14, "bold"),
            bg="#1e1e2e",
            fg="#cdd6f4"
        )
        active_title.pack(pady=(20, 10))
        
        self.active_text = scrolledtext.ScrolledText(
            left_frame,
            font=("Courier New", 10),
            bg="#181825",
            fg="#cdd6f4",
            height=8,
            relief=tk.FLAT
        )
        self.active_text.pack(fill=tk.BOTH, expand=True)
        
        # Right side - AI Insights
        right_frame = tk.Frame(content_frame, bg="#1e1e2e")
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
        
        ai_title = tk.Label(
            right_frame,
            text="🤖 AI Insights",
            font=("Arial", 16, "bold"),
            bg="#1e1e2e",
            fg="#cdd6f4"
        )
        ai_title.pack(pady=(0, 15))
        
        # AI status
        self.ai_status = tk.Label(
            right_frame,
            text="",
            font=("Arial", 10),
            bg="#1e1e2e",
            fg="#a6adc8"
        )
        self.ai_status.pack(pady=(0, 10))
        
        # AI insights display
        self.insights_text = scrolledtext.ScrolledText(
            right_frame,
            font=("Arial", 11),
            bg="#181825",
            fg="#cdd6f4",
            wrap=tk.WORD,
            relief=tk.FLAT
        )
        self.insights_text.pack(fill=tk.BOTH, expand=True)
        
        # Get summary button
        summary_btn = tk.Button(
            right_frame,
            text="📝 Gerar Resumo IA",
            command=self.generate_summary,
            font=("Arial", 11, "bold"),
            bg="#89b4fa",
            fg="#1e1e2e",
            activebackground="#74c7ec",
            relief=tk.FLAT,
            width=20,
            height=2,
            cursor="hand2"
        )
        summary_btn.pack(pady=(10, 0))
        
        # Bottom buttons
        button_frame = tk.Frame(self.frame, bg="#1e1e2e")
        button_frame.pack(pady=20)
        
        refresh_btn = tk.Button(
            button_frame,
            text="🔄 Atualizar",
            command=self.refresh_data,
            font=("Arial", 12, "bold"),
            bg="#a6e3a1",
            fg="#1e1e2e",
            activebackground="#94e2d5",
            relief=tk.FLAT,
            width=15,
            height=2,
            cursor="hand2"
        )
        refresh_btn.grid(row=0, column=0, padx=10)
        
        back_btn = tk.Button(
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
        back_btn.grid(row=0, column=1, padx=10)
    
    def create_stat_card(self, label, value, color):
        """Create a statistics card."""
        card_frame = tk.Frame(self.stats_frame, bg="#313244", relief=tk.FLAT, borderwidth=2)
        
        label_widget = tk.Label(
            card_frame,
            text=label,
            font=("Arial", 11),
            bg="#313244",
            fg="#cdd6f4",
            anchor="w"
        )
        label_widget.pack(side=tk.LEFT, padx=15, pady=10)
        
        value_widget = tk.Label(
            card_frame,
            text=value,
            font=("Arial", 14, "bold"),
            bg="#313244",
            fg=color,
            anchor="e"
        )
        value_widget.pack(side=tk.RIGHT, padx=15, pady=10)
        
        # Store reference to value label
        card_frame.value_label = value_widget
        
        return card_frame
    
    def refresh_data(self):
        """Refresh all data and statistics."""
        self.tracker.load()
        self.tracker.check_timeouts()
        
        # Get statistics
        stats = self.tracker.get_statistics()
        
        # Update stat cards
        self.stat_labels["active"].value_label.config(text=str(stats["active_count"]))
        self.stat_labels["today"].value_label.config(text=str(stats["total_today"]))
        self.stat_labels["registered"].value_label.config(text=str(stats["registered_today"]))
        self.stat_labels["unknown"].value_label.config(text=str(stats["unknown_today"]))
        
        avg_min = round(stats["avg_duration"] / 60, 1) if stats["avg_duration"] > 0 else 0
        self.stat_labels["avg_time"].value_label.config(text=f"{avg_min} min")
        
        # Update active people list
        self.active_text.delete(1.0, tk.END)
        active = self.tracker.get_all_active()
        
        if not active:
            self.active_text.insert(tk.END, "Nenhuma pessoa presente no momento.\n")
        else:
            for name, session in active.items():
                duration_min = round(session["duration_seconds"] / 60, 1)
                status = "✅" if session["is_registered"] else "⚠️"
                self.active_text.insert(
                    tk.END,
                    f"{status} {name}\n"
                    f"   Tempo: {duration_min} min | Detecções: {session['detection_count']}\n\n"
                )
        
        # Update AI status
        if ai_agent.enabled:
            self.ai_status.config(text="✅ AI Agent ativo", fg="#a6e3a1")
        else:
            self.ai_status.config(text="⚠️ AI Agent desativado (configure OPENAI_API_KEY)", fg="#f38ba8")
    
    def generate_summary(self):
        """Generate AI summary."""
        if not ai_agent.enabled:
            self.insights_text.delete(1.0, tk.END)
            self.insights_text.insert(
                tk.END,
                "⚠️ AI Agent não está configurado.\n\n"
                "Para ativar:\n"
                "1. Crie um arquivo .env\n"
                "2. Adicione: OPENAI_API_KEY=sua-chave\n"
                "3. Reinicie a aplicação\n"
            )
            return
        
        self.insights_text.delete(1.0, tk.END)
        self.insights_text.insert(tk.END, "🔄 Gerando resumo...\n\n")
        self.frame.update()
        
        summary = ai_agent.get_summary()
        
        self.insights_text.delete(1.0, tk.END)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.insights_text.insert(tk.END, f"📊 Resumo gerado às {timestamp}\n")
        self.insights_text.insert(tk.END, "=" * 50 + "\n\n")
        self.insights_text.insert(tk.END, summary + "\n")
    
    def show(self):
        """Display this screen."""
        self.frame.pack(fill=tk.BOTH, expand=True)
        self.refresh_data()
    
    def hide(self):
        """Hide this screen."""
        self.frame.pack_forget()

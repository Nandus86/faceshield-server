import tkinter as tk
from tkinter import font

class MenuScreen:
    """Main menu interface for the facial recognition application."""
    
    def __init__(self, root, on_recognize, on_register, on_view_logs, on_settings, on_manage, on_analytics):
        self.root = root
        self.on_recognize = on_recognize
        self.on_register = on_register
        self.on_view_logs = on_view_logs
        self.on_settings = on_settings
        self.on_manage = on_manage
        self.on_analytics = on_analytics
        
        self.frame = tk.Frame(root, bg="#1e1e2e")
        self.create_widgets()
    
    def create_widgets(self):
        """Create menu UI elements."""
        # Title
        title_font = font.Font(family="Arial", size=32, weight="bold")
        title = tk.Label(
            self.frame,
            text="Sistema de Reconhecimento Facial",
            font=title_font,
            bg="#1e1e2e",
            fg="#cdd6f4"
        )
        title.pack(pady=40)
        
        # Subtitle
        subtitle_font = font.Font(family="Arial", size=14)
        subtitle = tk.Label(
            self.frame,
            text="Selecione uma opção abaixo",
            font=subtitle_font,
            bg="#1e1e2e",
            fg="#a6adc8"
        )
        subtitle.pack(pady=10)
        
        # Button container
        button_container = tk.Frame(self.frame, bg="#1e1e2e")
        button_container.pack(pady=40)
        
        # Button styling
        button_font = font.Font(family="Arial", size=14, weight="bold")
        button_style = {
            "font": button_font,
            "width": 30,
            "height": 2,
            "relief": tk.FLAT,
            "cursor": "hand2",
            "borderwidth": 0
        }
        
        # Recognize button
        self.recognize_btn = tk.Button(
            button_container,
            text="🎥 Iniciar Reconhecimento em Tempo Real",
            command=self.on_recognize,
            bg="#89b4fa",
            fg="#1e1e2e",
            activebackground="#74c7ec",
            **button_style
        )
        self.recognize_btn.pack(pady=10)
        
        # Register button
        self.register_btn = tk.Button(
            button_container,
            text="📸 Cadastrar Nova Pessoa",
            command=self.on_register,
            bg="#a6e3a1",
            fg="#1e1e2e",
            activebackground="#94e2d5",
            **button_style
        )
        self.register_btn.pack(pady=10)
        
        # Manage button
        self.manage_btn = tk.Button(
            button_container,
            text="👥 Gerenciar Cadastros",
            command=self.on_manage,
            bg="#f9e2af",
            fg="#1e1e2e",
            activebackground="#f5c2e7",
            **button_style
        )
        self.manage_btn.pack(pady=10)
        
        # View logs button
        self.logs_btn = tk.Button(
            button_container,
            text="📄 Visualizar Logs",
            command=self.on_view_logs,
            bg="#f9e2af",
            fg="#1e1e2e",
            activebackground="#fab387",
            **button_style
        )
        self.logs_btn.pack(pady=10)
        
        # Analytics button
        self.analytics_btn = tk.Button(
            button_container,
            text="📊 Analytics & IA",
            command=self.on_analytics,
            bg="#89dceb",
            fg="#1e1e2e",
            activebackground="#74c7ec",
            **button_style
        )
        self.analytics_btn.pack(pady=10)
        
        # Settings button
        self.settings_btn = tk.Button(
            button_container,
            text="⚙️ Configurações",
            command=self.on_settings,
            bg="#cba6f7",
            fg="#1e1e2e",
            activebackground="#b4befe",
            **button_style
        )
        self.settings_btn.pack(pady=10)
        
        # Exit button
        self.exit_btn = tk.Button(
            button_container,
            text="❌ Sair",
            command=self.root.quit,
            bg="#f38ba8",
            fg="#1e1e2e",
            activebackground="#eba0ac",
            **button_style
        )
        self.exit_btn.pack(pady=10)
        
        # Footer
        footer = tk.Label(
            self.frame,
            text="Sistema de Reconhecimento Facial v1.0",
            font=("Arial", 10),
            bg="#1e1e2e",
            fg="#6c7086"
        )
        footer.pack(side=tk.BOTTOM, pady=20)
    
    def show(self):
        """Display this screen."""
        self.frame.pack(fill=tk.BOTH, expand=True)
    
    def hide(self):
        """Hide this screen."""
        self.frame.pack_forget()

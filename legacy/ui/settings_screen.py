import tkinter as tk
from tkinter import font, messagebox
import cv2
from PIL import Image, ImageTk
import config

class SettingsScreen:
    """Settings interface for configuring camera and other options."""
    
    def __init__(self, root, on_back):
        self.root = root
        self.on_back = on_back
        
        self.frame = tk.Frame(root, bg="#1e1e2e")
        self.camera = None
        self.running = False
        self.current_camera_index = config.CAMERA_INDEX
        
        self.create_widgets()
    
    def create_widgets(self):
        """Create settings UI elements."""
        # Title
        title_font = font.Font(family="Arial", size=24, weight="bold")
        title = tk.Label(
            self.frame,
            text="Configurações",
            font=title_font,
            bg="#1e1e2e",
            fg="#cdd6f4"
        )
        title.pack(pady=20)
        
        # Settings container
        settings_container = tk.Frame(self.frame, bg="#1e1e2e")
        settings_container.pack(pady=20, padx=40, fill=tk.BOTH, expand=True)
        
        # Camera settings section
        camera_section = tk.LabelFrame(
            settings_container,
            text="Configurações de Câmera",
            font=("Arial", 14, "bold"),
            bg="#313244",
            fg="#cdd6f4",
            relief=tk.FLAT,
            borderwidth=2
        )
        camera_section.pack(fill=tk.X, pady=10, padx=20, ipady=10)
        
        # Camera index selection
        index_frame = tk.Frame(camera_section, bg="#313244")
        index_frame.pack(pady=10, padx=20, fill=tk.X)
        
        camera_label = tk.Label(
            index_frame,
            text="Índice da Câmera:",
            font=("Arial", 12),
            bg="#313244",
            fg="#cdd6f4"
        )
        camera_label.pack(side=tk.LEFT, padx=(0, 10))
        
        # Spinbox for camera index
        self.camera_spinbox = tk.Spinbox(
            index_frame,
            from_=0,
            to=5,
            font=("Arial", 12),
            bg="#181825",
            fg="#cdd6f4",
            buttonbackground="#45475a",
            relief=tk.FLAT,
            width=10,
            command=self.on_camera_change
        )
        self.camera_spinbox.delete(0, tk.END)
        self.camera_spinbox.insert(0, str(self.current_camera_index))
        self.camera_spinbox.pack(side=tk.LEFT)
        
        help_label = tk.Label(
            index_frame,
            text="(0 = câmera padrão, 1, 2... = outras câmeras)",
            font=("Arial", 9),
            bg="#313244",
            fg="#6c7086"
        )
        help_label.pack(side=tk.LEFT, padx=(10, 0))
        
        # Camera preview
        preview_frame = tk.Frame(camera_section, bg="#313244")
        preview_frame.pack(pady=10, padx=20)
        
        self.preview_label = tk.Label(
            preview_frame,
            bg="#181825",
            width=480,
            height=360,
            text="Prévia da câmera aparecerá aqui",
            font=("Arial", 11),
            fg="#6c7086"
        )
        self.preview_label.pack()
        
        # Test button
        button_frame = tk.Frame(camera_section, bg="#313244")
        button_frame.pack(pady=10)
        
        self.test_btn = tk.Button(
            button_frame,
            text="🎥 Testar Câmera",
            command=self.test_camera,
            font=("Arial", 12, "bold"),
            bg="#89b4fa",
            fg="#1e1e2e",
            activebackground="#74c7ec",
            relief=tk.FLAT,
            width=15,
            height=2,
            cursor="hand2"
        )
        self.test_btn.grid(row=0, column=0, padx=5)
        
        self.stop_test_btn = tk.Button(
            button_frame,
            text="⏹️ Parar Teste",
            command=self.stop_test,
            font=("Arial", 12, "bold"),
            bg="#f38ba8",
            fg="#1e1e2e",
            activebackground="#eba0ac",
            relief=tk.FLAT,
            width=15,
            height=2,
            cursor="hand2",
            state=tk.DISABLED
        )
        self.stop_test_btn.grid(row=0, column=1, padx=5)
        
        # Status label
        self.status_label = tk.Label(
            camera_section,
            text="Selecione o índice correto e teste a câmera",
            font=("Arial", 11),
            bg="#313244",
            fg="#a6adc8"
        )
        self.status_label.pack(pady=10)
        
        # Recognition settings section
        recognition_section = tk.LabelFrame(
            settings_container,
            text="Configurações de Reconhecimento",
            font=("Arial", 14, "bold"),
            bg="#313244",
            fg="#cdd6f4",
            relief=tk.FLAT,
            borderwidth=2
        )
        recognition_section.pack(fill=tk.X, pady=10, padx=20, ipady=10)
        
        # Confidence threshold
        confidence_frame = tk.Frame(recognition_section, bg="#313244")
        confidence_frame.pack(pady=10, padx=20, fill=tk.X)
        
        confidence_label = tk.Label(
            confidence_frame,
            text="Limite de Confiança:",
            font=("Arial", 12),
            bg="#313244",
            fg="#cdd6f4"
        )
        confidence_label.pack(side=tk.LEFT, padx=(0, 10))
        
        self.confidence_spinbox = tk.Spinbox(
            confidence_frame,
            from_=10,
            to=100,
            font=("Arial", 12),
            bg="#181825",
            fg="#cdd6f4",
            buttonbackground="#45475a",
            relief=tk.FLAT,
            width=10
        )
        self.confidence_spinbox.delete(0, tk.END)
        self.confidence_spinbox.insert(0, str(config.CONFIDENCE_THRESHOLD))
        self.confidence_spinbox.pack(side=tk.LEFT)
        
        confidence_help = tk.Label(
            confidence_frame,
            text="(menor = mais restrito, 50 recomendado)",
            font=("Arial", 9),
            bg="#313244",
            fg="#6c7086"
        )
        confidence_help.pack(side=tk.LEFT, padx=(10, 0))
        
        # Bottom buttons
        bottom_frame = tk.Frame(self.frame, bg="#1e1e2e")
        bottom_frame.pack(pady=20)
        
        self.save_btn = tk.Button(
            bottom_frame,
            text="💾 Salvar Configurações",
            command=self.save_settings,
            font=("Arial", 12, "bold"),
            bg="#a6e3a1",
            fg="#1e1e2e",
            activebackground="#94e2d5",
            relief=tk.FLAT,
            width=20,
            height=2,
            cursor="hand2"
        )
        self.save_btn.grid(row=0, column=0, padx=10)
        
        self.back_btn = tk.Button(
            bottom_frame,
            text="🔙 Voltar ao Menu",
            command=self.back_to_menu,
            font=("Arial", 12, "bold"),
            bg="#6c7086",
            fg="#cdd6f4",
            activebackground="#585b70",
            relief=tk.FLAT,
            width=20,
            height=2,
            cursor="hand2"
        )
        self.back_btn.grid(row=0, column=1, padx=10)
    
    def on_camera_change(self):
        """Handle camera index change."""
        if self.running:
            self.stop_test()
    
    def test_camera(self):
        """Test the selected camera."""
        try:
            camera_index = int(self.camera_spinbox.get())
            self.current_camera_index = camera_index
            
            if getattr(config, 'USE_A9_CAMERA', False):
                try:
                    from a9_camera_adapter import A9VideoCapture
                    self.camera = A9VideoCapture()
                except ImportError:
                    self.camera = cv2.VideoCapture(camera_index)
            else:
                self.camera = cv2.VideoCapture(camera_index)
            
            if not self.camera.isOpened():
                messagebox.showerror(
                    "Erro na Câmera",
                    f"Não foi possível abrir a câmera no índice {camera_index}.\n"
                    "Tente outro índice."
                )
                return
            
            self.running = True
            self.test_btn.config(state=tk.DISABLED)
            self.stop_test_btn.config(state=tk.NORMAL)
            self.camera_spinbox.config(state=tk.DISABLED)
            self.status_label.config(text="Câmera ativa - teste em andamento", fg="#a6e3a1")
            
            self.update_preview()
            
        except ValueError:
            messagebox.showerror(
                "Valor Inválido",
                "Por favor, insira um número válido para o índice da câmera."
            )
    
    def stop_test(self):
        """Stop camera test."""
        self.running = False
        if self.camera:
            self.camera.release()
            self.camera = None
        
        self.test_btn.config(state=tk.NORMAL)
        self.stop_test_btn.config(state=tk.DISABLED)
        self.camera_spinbox.config(state=tk.NORMAL)
        self.preview_label.config(image="", text="Prévia da câmera aparecerá aqui")
        self.status_label.config(text="Teste parado", fg="#a6adc8")
    
    def update_preview(self):
        """Update camera preview."""
        if not self.running or not self.camera:
            return
        
        ret, frame = self.camera.read()
        
        if ret:
            # Convert to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Resize to fit display
            display_frame = cv2.resize(frame_rgb, (480, 360))
            
            # Convert to PhotoImage
            img = Image.fromarray(display_frame)
            photo = ImageTk.PhotoImage(image=img)
            
            self.preview_label.configure(image=photo, text="")
            self.preview_label.image = photo
        else:
            self.stop_test()
            messagebox.showerror(
                "Erro na Câmera",
                "A câmera parou de responder durante o teste."
            )
            return
        
        # Schedule next update
        if self.running:
            self.preview_label.after(30, self.update_preview)
    
    def save_settings(self):
        """Save settings to config file."""
        try:
            camera_index = int(self.camera_spinbox.get())
            confidence = int(self.confidence_spinbox.get())
            
            # Update config file
            config_path = "config.py"
            with open(config_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            with open(config_path, "w", encoding="utf-8") as f:
                for line in lines:
                    if line.startswith("CAMERA_INDEX"):
                        f.write(f"CAMERA_INDEX = {camera_index}\n")
                    elif line.startswith("CONFIDENCE_THRESHOLD"):
                        f.write(f"CONFIDENCE_THRESHOLD = {confidence}  # Lower is better (0-100), below this is considered a match\n")
                    else:
                        f.write(line)
            
            # Update runtime config
            config.CAMERA_INDEX = camera_index
            config.CONFIDENCE_THRESHOLD = confidence
            
            messagebox.showinfo(
                "Configurações Salvas",
                "As configurações foram salvas com sucesso!\n"
                "Reinicie a aplicação para aplicar todas as mudanças."
            )
            
        except ValueError:
            messagebox.showerror(
                "Erro de Validação",
                "Por favor, insira valores numéricos válidos."
            )
        except Exception as e:
            messagebox.showerror(
                "Erro ao Salvar",
                f"Não foi possível salvar as configurações:\n{e}"
            )
    
    def back_to_menu(self):
        """Return to main menu."""
        if self.running:
            self.stop_test()
        self.on_back()
    
    def show(self):
        """Display this screen."""
        self.frame.pack(fill=tk.BOTH, expand=True)
    
    def hide(self):
        """Hide this screen."""
        if self.running:
            self.stop_test()
        self.frame.pack_forget()

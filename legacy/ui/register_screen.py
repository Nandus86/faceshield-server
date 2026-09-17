import tkinter as tk
from tkinter import font, messagebox, ttk
import cv2
from PIL import Image, ImageTk
from core.face_detector import FaceDetector

class RegisterScreen:
    """Registration interface for adding new people to the database."""
    
    def __init__(self, root, on_back):
        self.root = root
        self.on_back = on_back
        self.face_detector = FaceDetector()
        
        self.frame = tk.Frame(root, bg="#1e1e2e")
        self.camera = None
        self.running = False
        self.captured_frame = None
        
        self.create_widgets()
    
    def create_widgets(self):
        """Create registration UI elements."""
        # Title
        title_font = font.Font(family="Arial", size=24, weight="bold")
        title = tk.Label(
            self.frame,
            text="Cadastrar Nova Pessoa",
            font=title_font,
            bg="#1e1e2e",
            fg="#cdd6f4"
        )
        title.pack(pady=20)
        
        # Input frame
        input_frame = tk.Frame(self.frame, bg="#1e1e2e")
        input_frame.pack(pady=10)
        
        # Mode selection
        mode_label = tk.Label(
            input_frame,
            text="Modo:",
            font=("Arial", 12),
            bg="#1e1e2e",
            fg="#cdd6f4"
        )
        mode_label.grid(row=0, column=0, padx=10, pady=5, sticky="e")
        
        self.mode_var = tk.StringVar(value="new")
        
        mode_frame = tk.Frame(input_frame, bg="#1e1e2e")
        mode_frame.grid(row=0, column=1, padx=10, pady=5, sticky="w")
        
        self.new_person_radio = tk.Radiobutton(
            mode_frame,
            text="Nova Pessoa",
            variable=self.mode_var,
            value="new",
            command=self.on_mode_change,
            font=("Arial", 11),
            bg="#1e1e2e",
            fg="#cdd6f4",
            selectcolor="#313244",
            activebackground="#1e1e2e",
            activeforeground="#cdd6f4"
        )
        self.new_person_radio.pack(side=tk.LEFT, padx=5)
        
        self.add_photo_radio = tk.Radiobutton(
            mode_frame,
            text="Adicionar Foto a Pessoa Existente",
            variable=self.mode_var,
            value="add",
            command=self.on_mode_change,
            font=("Arial", 11),
            bg="#1e1e2e",
            fg="#cdd6f4",
            selectcolor="#313244",
            activebackground="#1e1e2e",
            activeforeground="#cdd6f4"
        )
        self.add_photo_radio.pack(side=tk.LEFT, padx=5)
        
        # Name label
        name_label = tk.Label(
            input_frame,
            text="Nome:",
            font=("Arial", 12),
            bg="#1e1e2e",
            fg="#cdd6f4"
        )
        name_label.grid(row=1, column=0, padx=10, pady=5, sticky="e")
        
        # Name entry (for new person)
        self.name_entry = tk.Entry(
            input_frame,
            font=("Arial", 12),
            width=30,
            bg="#313244",
            fg="#cdd6f4",
            insertbackground="#cdd6f4",
            relief=tk.FLAT,
            borderwidth=2
        )
        self.name_entry.grid(row=1, column=1, padx=10, pady=5)
        
        # Name dropdown (for existing person)
        self.name_dropdown = ttk.Combobox(
            input_frame,
            font=("Arial", 12),
            width=28,
            state="readonly"
        )
        self.name_dropdown.grid(row=1, column=1, padx=10, pady=5)
        self.name_dropdown.grid_remove()  # Hide initially
        
        # Camera preview
        self.camera_label = tk.Label(
            self.frame,
            bg="#181825",
            width=640,
            height=480
        )
        self.camera_label.pack(pady=20)
        
        # Button frame
        button_frame = tk.Frame(self.frame, bg="#1e1e2e")
        button_frame.pack(pady=10)
        
        # Capture button
        self.capture_btn = tk.Button(
            button_frame,
            text="📸 Capturar Foto",
            command=self.capture_photo,
            font=("Arial", 12, "bold"),
            bg="#a6e3a1",
            fg="#1e1e2e",
            activebackground="#94e2d5",
            relief=tk.FLAT,
            width=15,
            height=2,
            cursor="hand2"
        )
        self.capture_btn.grid(row=0, column=0, padx=10)
        
        # Save button
        self.save_btn = tk.Button(
            button_frame,
            text="💾 Salvar Cadastro",
            command=self.save_registration,
            font=("Arial", 12, "bold"),
            bg="#89b4fa",
            fg="#1e1e2e",
            activebackground="#74c7ec",
            relief=tk.FLAT,
            width=15,
            height=2,
            cursor="hand2",
            state=tk.DISABLED
        )
        self.save_btn.grid(row=0, column=1, padx=10)
        
        # Back button
        self.back_btn = tk.Button(
            button_frame,
            text="🔙 Voltar ao Menu",
            command=self.back_to_menu,
            font=("Arial", 12, "bold"),
            bg="#6c7086",
            fg="#cdd6f4",
            activebackground="#585b70",
            relief=tk.FLAT,
            width=15,
            height=2,
            cursor="hand2"
        )
        self.back_btn.grid(row=0, column=2, padx=10)
        
        # Status label
        self.status_label = tk.Label(
            self.frame,
            text="Aguardando captura...",
            font=("Arial", 11),
            bg="#1e1e2e",
            fg="#a6adc8"
        )
        self.status_label.pack(pady=10)
    
    def on_mode_change(self):
        """Handle mode change between new person and add photo."""
        mode = self.mode_var.get()
        
        if mode == "new":
            self.name_entry.grid()
            self.name_dropdown.grid_remove()
        else:
            self.name_entry.grid_remove()
            self.name_dropdown.grid()
            self.update_name_list()
    
    def update_name_list(self):
        """Update the dropdown with existing names."""
        names = self.face_detector.database.get_all_names()
        self.name_dropdown['values'] = sorted(names)
        if names:
            self.name_dropdown.current(0)
    
    def start_camera(self):
        """Start the camera feed."""
        import config
        from tkinter import messagebox
        if getattr(config, 'USE_A9_CAMERA', False):
            try:
                from a9_camera_adapter import A9VideoCapture
                self.camera = A9VideoCapture()
            except ImportError:
                self.camera = cv2.VideoCapture(config.CAMERA_INDEX)
        else:
            self.camera = cv2.VideoCapture(config.CAMERA_INDEX)
        
        if not self.camera.isOpened():
            messagebox.showerror(
                "Erro na Câmera",
                f"Não foi possível acessar a câmera no índice {config.CAMERA_INDEX}.\n\n"
                "Soluções:\n"
                "1. Execute 'python diagnostico_camera.py' para encontrar câmeras\n"
                "2. Vá em Configurações e teste diferentes índices\n"
                "3. Feche outros programas que possam estar usando a câmera\n"
                "4. Verifique as permissões de câmera no Windows"
            )
            self.back_to_menu()
            return
        
        self.running = True
        self.update_camera()
    
    def stop_camera(self):
        """Stop the camera feed."""
        self.running = False
        if self.camera:
            self.camera.release()
            self.camera = None
    
    def update_camera(self):
        """Update camera preview."""
        if not self.running or not self.camera:
            return
        
        ret, frame = self.camera.read()
        
        if ret and frame is not None:
            # Convert to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Resize to fit display
            display_frame = cv2.resize(frame_rgb, (640, 480))
            
            # Convert to PhotoImage
            img = Image.fromarray(display_frame)
            photo = ImageTk.PhotoImage(image=img)
            
            self.camera_label.configure(image=photo)
            self.camera_label.image = photo
        
        # Schedule next update
        if self.running:
            self.camera_label.after(10, self.update_camera)
    
    def capture_photo(self):
        """Capture current frame."""
        if not self.camera:
            return
        
        ret, frame = self.camera.read()
        
        if ret:
            # Check if face is detected
            encoding = self.face_detector.encode_face(frame)
            
            if encoding is None:
                messagebox.showwarning(
                    "Nenhum Rosto Detectado",
                    "Não foi possível detectar um rosto na imagem. Tente novamente."
                )
                return
            
            self.captured_frame = frame
            self.save_btn.config(state=tk.NORMAL)
            self.status_label.config(text="Foto capturada! Preencha o nome e clique em Salvar.", fg="#a6e3a1")
    
    def save_registration(self):
        """Save the registration."""
        mode = self.mode_var.get()
        
        if mode == "new":
            name = self.name_entry.get().strip()
        else:
            name = self.name_dropdown.get().strip()
        
        if not name:
            messagebox.showwarning(
                "Nome Obrigatório",
                "Por favor, informe o nome da pessoa."
            )
            return
        
        if self.captured_frame is None:
            messagebox.showwarning(
                "Foto Não Capturada",
                "Por favor, capture uma foto antes de salvar."
            )
            return
        
        # Register the face
        success = self.face_detector.register_face(name, self.captured_frame)
        
        if success:
            if mode == "new":
                messagebox.showinfo(
                    "Cadastro Realizado",
                    f"A pessoa '{name}' foi cadastrada com sucesso!"
                )
            else:
                photo_count = self.face_detector.database.get_person_info(name).get("photo_count", 1)
                messagebox.showinfo(
                    "Foto Adicionada",
                    f"Foto adicionada para '{name}'!\nTotal: {photo_count} foto(s)."
                )
            
            # Reset form
            self.name_entry.delete(0, tk.END)
            self.captured_frame = None
            self.save_btn.config(state=tk.DISABLED)
            self.status_label.config(text="Aguardando captura...", fg="#a6adc8")
        else:
            messagebox.showerror(
                "Erro no Cadastro",
                "Não foi possível realizar o cadastro. Tente novamente."
            )
    
    def back_to_menu(self):
        """Return to main menu."""
        self.stop_camera()
        self.on_back()
    
    def show(self):
        """Display this screen."""
        self.frame.pack(fill=tk.BOTH, expand=True)
        self.start_camera()
    
    def hide(self):
        """Hide this screen."""
        self.stop_camera()
        self.frame.pack_forget()

import tkinter as tk
from tkinter import font, scrolledtext
import cv2
from PIL import Image, ImageTk
from core.face_detector import FaceDetector
from core.presence_tracker import PresenceTracker
from ai_agent.agent import agent as ai_agent
from utils.logger import get_recent_logs
import config

class RecognitionScreen:
    """Real-time face recognition interface."""
    
    def __init__(self, root, on_back):
        self.root = root
        self.on_back = on_back
        self.face_detector = FaceDetector()
        self.tracker = PresenceTracker()
        
        self.frame = tk.Frame(root, bg="#1e1e2e")
        self.camera = None
        self.running = False
        self.last_analysis_time = 0
        
        self.create_widgets()
    
    def create_widgets(self):
        """Create recognition UI elements."""
        # Title
        title_font = font.Font(family="Arial", size=24, weight="bold")
        title = tk.Label(
            self.frame,
            text="Reconhecimento em Tempo Real",
            font=title_font,
            bg="#1e1e2e",
            fg="#cdd6f4"
        )
        title.pack(pady=20)
        
        # Main content frame
        content_frame = tk.Frame(self.frame, bg="#1e1e2e")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20)
        
        # Left side - Camera
        camera_frame = tk.Frame(content_frame, bg="#1e1e2e")
        camera_frame.pack(side=tk.LEFT, padx=10)
        
        self.camera_label = tk.Label(
            camera_frame,
            bg="#181825",
            width=640,
            height=480
        )
        self.camera_label.pack()
        
        # Right side - Recent detections
        log_frame = tk.Frame(content_frame, bg="#1e1e2e")
        log_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        
        log_title = tk.Label(
            log_frame,
            text="Detecções Recentes",
            font=("Arial", 14, "bold"),
            bg="#1e1e2e",
            fg="#cdd6f4"
        )
        log_title.pack(pady=(0, 10))
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            font=("Courier New", 9),
            bg="#181825",
            fg="#cdd6f4",
            height=12,
            width=40,
            relief=tk.FLAT,
            borderwidth=2
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # AI Insights box
        insights_frame = tk.Frame(log_frame, bg="#1e1e2e")
        insights_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        insights_title = tk.Label(
            insights_frame,
            text="🤖 AI Insights",
            font=("Arial", 12, "bold"),
            bg="#1e1e2e",
            fg="#cdd6f4"
        )
        insights_title.pack(pady=(0, 5))
        
        self.insights_text = scrolledtext.ScrolledText(
            insights_frame,
            font=("Arial", 10),
            bg="#181825",
            fg="#a6e3a1",
            height=10,
            width=40,
            relief=tk.FLAT,
            borderwidth=2,
            wrap=tk.WORD
        )
        self.insights_text.pack(fill=tk.BOTH, expand=True)
        
        # Button frame
        button_frame = tk.Frame(self.frame, bg="#1e1e2e")
        button_frame.pack(pady=20)
        
        # Stop button
        self.stop_btn = tk.Button(
            button_frame,
            text="⏹️ Parar Reconhecimento",
            command=self.back_to_menu,
            font=("Arial", 12, "bold"),
            bg="#f38ba8",
            fg="#1e1e2e",
            activebackground="#eba0ac",
            relief=tk.FLAT,
            width=25,
            height=2,
            cursor="hand2"
        )
        self.stop_btn.pack()
        
        # Status label
        self.status_label = tk.Label(
            self.frame,
            text="Câmera ativa - Monitorando...",
            font=("Arial", 11),
            bg="#1e1e2e",
            fg="#a6e3a1"
        )
        self.status_label.pack(pady=10)
    
    def start_camera(self):
        """Start the camera feed and recognition."""
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
        self.update_logs()
    
    def stop_camera(self):
        """Stop the camera feed."""
        self.running = False
        if self.camera:
            self.camera.release()
            self.camera = None
    
    def update_camera(self):
        """Update camera with face detection."""
        if not self.running or not self.camera:
            return
        
        ret, frame = self.camera.read()
        
        if ret and frame is not None:
            # Detect and recognize faces
            results = self.face_detector.detect_and_recognize(frame)
            
            # Process results
            for name, (top, right, bottom, left) in results:
                # Update presence tracker
                is_registered = (name != "Desconhecido")
                self.tracker.update_detection(name, is_registered)
                
                # AI analysis (periodically)
                import time
                current_time = time.time()
                if config.AGENT_ENABLED and (current_time - self.last_analysis_time) > config.ANALYSIS_INTERVAL:
                    self.last_analysis_time = current_time
                    self.analyze_with_ai(name, is_registered)
                
                # Choose color based on recognition
                color = (0, 255, 0) if name != "Desconhecido" else (0, 0, 255)
                
                # Draw rectangle
                cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                
                # Draw name background
                cv2.rectangle(frame, (left, bottom - 35), (right, bottom), color, cv2.FILLED)
                
                # Draw name text
                cv2.putText(
                    frame,
                    name,
                    (left + 6, bottom - 6),
                    cv2.FONT_HERSHEY_DUPLEX,
                    0.6,
                    (255, 255, 255),
                    1
                )
            
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
    
    def update_logs(self):
        """Update the log display."""
        if not self.running:
            return
        
        # Check for timeouts
        self.tracker.check_timeouts()
        
        # Get recent logs
        logs = get_recent_logs(15)
        
        # Update text widget
        self.log_text.delete(1.0, tk.END)
        self.log_text.insert(tk.END, "".join(logs))
        self.log_text.see(tk.END)
        
        # Schedule next update
        if self.running:
            self.log_text.after(2000, self.update_logs)  # Update every 2 seconds
    
    def analyze_with_ai(self, name: str, is_registered: bool):
        """Analyze detection with AI agent."""
        if not ai_agent.enabled:
            return
        
        try:
            result = ai_agent.analyze_detection(name, is_registered)
            
            if result.get("analysis"):
                timestamp = __import__("datetime").datetime.now().strftime("%H:%M:%S")
                self.insights_text.insert(tk.END, f"\n[{timestamp}] {name}\n")
                self.insights_text.insert(tk.END, f"{result['analysis']}\n")
                self.insights_text.insert(tk.END, "-" * 40 + "\n")
                self.insights_text.see(tk.END)
        except Exception as e:
            print(f"Erro na análise AI: {e}")
    
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
